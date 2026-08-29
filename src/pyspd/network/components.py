"""Class-based Pyomo components for the Gate 5 AC network and security model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuildContext, ModelComponent
from pyspd.network.data import AC_NETWORK_FORMULATION_ID, NetworkCase, NetworkData

type Key = tuple[str, ...]

_SUPPORTED = frozenset({AC_NETWORK_FORMULATION_ID})


def _case(context: BuildContext) -> NetworkCase:
    if not isinstance(context.case_data, NetworkCase):
        raise TypeError("AC-network components require NetworkCase")
    return context.case_data


def _network(context: BuildContext) -> NetworkData:
    data = _case(context).network
    assert data is not None
    return data


class NetworkDomainsComponent(ModelComponent):
    name = "network_domains"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains"})
    provides = frozenset({"network_data", "network_domains"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _network(context)
        block = pyo.Block(concrete=True)
        context.model.add_component("NetworkDomains", block)
        block.Bus = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.buses))
        block.Branch = pyo.Set(
            dimen=3, ordered=True, initialize=sorted(data.branches)
        )
        block.ACBranch = pyo.Set(
            dimen=3, ordered=True, initialize=sorted(data.ac_branches)
        )
        block.Direction = pyo.Set(
            ordered=True, initialize=("forward", "backward")
        )
        block.DirectedACBranch = pyo.Set(
            dimen=4,
            ordered=True,
            initialize=sorted(
                (*branch, direction)
                for branch in data.ac_branches
                for direction in ("forward", "backward")
            ),
        )
        block.ACLossSegment = pyo.Set(
            dimen=5,
            ordered=True,
            initialize=sorted(data.valid_ac_loss_segments),
        )
        block.BranchConstraint = pyo.Set(
            dimen=3,
            ordered=True,
            initialize=sorted(data.branch_constraints),
        )
        block.MarketNodeConstraint = pyo.Set(
            dimen=3,
            ordered=True,
            initialize=sorted(data.market_node_constraints),
        )
        return {"network_data": data, "network_domains": block}


class ACNetworkComponent(ModelComponent):
    name = "ac_network"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "core_data",
            "domains",
            "network_data",
            "network_domains",
            "generation",
            "purchase",
            "energy_scarcity_node",
        }
    )
    provides = frozenset(
        {
            "net_injection",
            "branch_flow",
            "node_angle",
            "directed_branch_flow",
            "directed_branch_loss",
            "branch_flow_block",
            "branch_loss_block",
            "balance_deficit",
            "balance_surplus",
            "branch_flow_surplus",
            "network_flow_balance",
            "energy_balance",
            "branch_maximum_flow",
            "branch_flow_definition",
            "linear_load_flow",
            "branch_block_limit",
            "directed_branch_flow_definition",
            "branch_loss_calculation",
            "directed_branch_loss_definition",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _network(context)
        network = context.artifacts["network_domains"]
        generation = context.artifacts["generation"]
        purchase = context.artifacts["purchase"]
        scarcity = context.artifacts["energy_scarcity_node"]
        block = pyo.Block(concrete=True)
        context.model.add_component("ACNetwork", block)

        block.ACNodeNetInjection = pyo.Var(network.Bus, domain=pyo.Reals)
        block.ACBranchFlow = pyo.Var(network.ACBranch, domain=pyo.Reals)
        block.ACNodeAngle = pyo.Var(network.Bus, domain=pyo.Reals)
        for bus in data.reference_buses:
            block.ACNodeAngle[bus].fix(0.0)
        block.ACBranchFlowDirected = pyo.Var(
            network.DirectedACBranch, domain=pyo.NonNegativeReals
        )
        block.ACBranchLossesDirected = pyo.Var(
            network.DirectedACBranch, domain=pyo.NonNegativeReals
        )
        block.ACBranchFlowBlockDirected = pyo.Var(
            network.ACLossSegment, domain=pyo.NonNegativeReals
        )
        block.ACBranchLossesBlockDirected = pyo.Var(
            network.ACLossSegment, domain=pyo.NonNegativeReals
        )
        block.DeficitBusGeneration = pyo.Var(
            network.Bus, domain=pyo.NonNegativeReals
        )
        block.SurplusBusGeneration = pyo.Var(
            network.Bus, domain=pyo.NonNegativeReals
        )
        block.SurplusBranchFlow = pyo.Var(
            network.Branch, domain=pyo.NonNegativeReals
        )

        def sending(branch: Key, bus: Key, direction: str) -> bool:
            endpoint = (
                data.branch_from_bus
                if direction == "forward"
                else data.branch_to_bus
            )
            return (*branch, bus[2]) in endpoint

        def receiving(branch: Key, bus: Key, direction: str) -> bool:
            endpoint = (
                data.branch_to_bus
                if direction == "forward"
                else data.branch_from_bus
            )
            return (*branch, bus[2]) in endpoint

        def flow_balance(_b: pyo.Block, ca: str, dt: str, bus: str) -> Any:
            bus_key = (ca, dt, bus)
            return _b.ACNodeNetInjection[bus_key] == sum(
                _b.ACBranchFlowDirected[*branch, direction]
                for branch in data.ac_branches
                for direction in ("forward", "backward")
                if sending(branch, bus_key, direction)
            ) - sum(
                _b.ACBranchFlowDirected[*branch, direction]
                for branch in data.ac_branches
                for direction in ("forward", "backward")
                if receiving(branch, bus_key, direction)
            )

        block.ACNodeNetInjectionDefinition1 = pyo.Constraint(
            network.Bus, rule=flow_balance
        )

        def bus_balance(_b: pyo.Block, ca: str, dt: str, bus: str) -> Any:
            bus_key = (ca, dt, bus)
            supply = sum(
                data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * generation[ca, dt, offer]
                for o_ca, o_dt, offer, node in data.offer_node
                if (o_ca, o_dt) == (ca, dt)
                and (ca, dt, node, bus) in data.node_bus
            )
            demand_bid = sum(
                data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * purchase[ca, dt, bid]
                for b_ca, b_dt, bid, node in data.bid_node
                if (b_ca, b_dt) == (ca, dt)
                and (ca, dt, node, bus) in data.node_bus
            )
            load = sum(
                data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * data.node_load[(ca, dt, node)]
                for n_ca, n_dt, node, n_bus in data.node_bus
                if (n_ca, n_dt, n_bus) == bus_key
            )
            dynamic_loss = sum(
                (
                    data.receiving_end_loss_proportion
                    if receiving(branch, bus_key, direction)
                    else 1.0 - data.receiving_end_loss_proportion
                )
                * _b.ACBranchLossesDirected[*branch, direction]
                for branch in data.ac_branches
                for direction in ("forward", "backward")
                if receiving(branch, bus_key, direction)
                or sending(branch, bus_key, direction)
            )
            fixed_loss = sum(
                0.5 * data.branch_fixed_loss[branch]
                for branch in data.branches
                if (*branch, bus) in data.branch_bus_connect
            )
            scarcity_supply = sum(
                data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * scarcity[ca, dt, node]
                for n_ca, n_dt, node, n_bus in data.node_bus
                if (n_ca, n_dt, n_bus) == bus_key
            )
            return _b.ACNodeNetInjection[bus_key] == (
                supply
                - demand_bid
                - load
                - dynamic_loss
                - fixed_loss
                + _b.DeficitBusGeneration[bus_key]
                - _b.SurplusBusGeneration[bus_key]
                + scarcity_supply
            )

        block.ACNodeNetInjectionDefinition2 = pyo.Constraint(
            network.Bus, rule=bus_balance
        )

        def maximum_flow(
            _b: pyo.Block, ca: str, dt: str, branch: str, direction: str
        ) -> Any:
            if not data.use_ac_branch_limits:
                return pyo.Constraint.Skip
            key = (ca, dt, branch)
            return (
                _b.ACBranchFlowDirected[*key, direction]
                - _b.SurplusBranchFlow[key]
                <= data.branch_capacity[*key, direction]
            )

        block.ACBranchMaximumFlow = pyo.Constraint(
            network.DirectedACBranch, rule=maximum_flow
        )
        block.ACBranchFlowDefinition = pyo.Constraint(
            network.ACBranch,
            rule=lambda _b, ca, dt, branch: (
                _b.ACBranchFlow[ca, dt, branch]
                == _b.ACBranchFlowDirected[ca, dt, branch, "forward"]
                - _b.ACBranchFlowDirected[ca, dt, branch, "backward"]
            ),
        )

        def load_flow(_b: pyo.Block, ca: str, dt: str, branch: str) -> Any:
            key = (ca, dt, branch)
            from_bus = next(
                bus
                for b_ca, b_dt, b_branch, bus in data.branch_from_bus
                if (b_ca, b_dt, b_branch) == key
            )
            to_bus = next(
                bus
                for b_ca, b_dt, b_branch, bus in data.branch_to_bus
                if (b_ca, b_dt, b_branch) == key
            )
            return _b.ACBranchFlow[key] == data.branch_susceptance[key] * (
                _b.ACNodeAngle[ca, dt, from_bus]
                - _b.ACNodeAngle[ca, dt, to_bus]
            )

        block.LinearLoadFlow = pyo.Constraint(network.ACBranch, rule=load_flow)
        block.ACBranchBlockLimit = pyo.Constraint(
            network.ACLossSegment,
            rule=lambda _b, ca, dt, branch, segment, direction: (
                _b.ACBranchFlowBlockDirected[ca, dt, branch, segment, direction]
                <= data.ac_loss_segment_mw[
                    ca, dt, branch, segment, direction
                ]
            ),
        )
        block.ACDirectedBranchFlowDefinition = pyo.Constraint(
            network.DirectedACBranch,
            rule=lambda _b, ca, dt, branch, direction: (
                _b.ACBranchFlowDirected[ca, dt, branch, direction]
                == sum(
                    _b.ACBranchFlowBlockDirected[key]
                    for key in network.ACLossSegment
                    if key[:3] == (ca, dt, branch) and key[4] == direction
                )
            ),
        )
        block.ACBranchLossCalculation = pyo.Constraint(
            network.ACLossSegment,
            rule=lambda _b, ca, dt, branch, segment, direction: (
                _b.ACBranchLossesBlockDirected[
                    ca, dt, branch, segment, direction
                ]
                == _b.ACBranchFlowBlockDirected[
                    ca, dt, branch, segment, direction
                ]
                * data.ac_loss_segment_factor[
                    ca, dt, branch, segment, direction
                ]
            ),
        )
        block.ACDirectedBranchLossDefinition = pyo.Constraint(
            network.DirectedACBranch,
            rule=lambda _b, ca, dt, branch, direction: (
                _b.ACBranchLossesDirected[ca, dt, branch, direction]
                == sum(
                    _b.ACBranchLossesBlockDirected[key]
                    for key in network.ACLossSegment
                    if key[:3] == (ca, dt, branch) and key[4] == direction
                )
            ),
        )
        return {
            "net_injection": block.ACNodeNetInjection,
            "branch_flow": block.ACBranchFlow,
            "node_angle": block.ACNodeAngle,
            "directed_branch_flow": block.ACBranchFlowDirected,
            "directed_branch_loss": block.ACBranchLossesDirected,
            "branch_flow_block": block.ACBranchFlowBlockDirected,
            "branch_loss_block": block.ACBranchLossesBlockDirected,
            "balance_deficit": block.DeficitBusGeneration,
            "balance_surplus": block.SurplusBusGeneration,
            "branch_flow_surplus": block.SurplusBranchFlow,
            "network_flow_balance": block.ACNodeNetInjectionDefinition1,
            "energy_balance": block.ACNodeNetInjectionDefinition2,
            "branch_maximum_flow": block.ACBranchMaximumFlow,
            "branch_flow_definition": block.ACBranchFlowDefinition,
            "linear_load_flow": block.LinearLoadFlow,
            "branch_block_limit": block.ACBranchBlockLimit,
            "directed_branch_flow_definition": block.ACDirectedBranchFlowDefinition,
            "branch_loss_calculation": block.ACBranchLossCalculation,
            "directed_branch_loss_definition": block.ACDirectedBranchLossDefinition,
        }


class NetworkSecurityComponent(ModelComponent):
    name = "network_security"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "network_data",
            "network_domains",
            "branch_flow",
            "generation",
            "purchase",
        }
    )
    provides = frozenset(
        {
            "branch_constraint_deficit",
            "branch_constraint_surplus",
            "market_node_constraint_deficit",
            "market_node_constraint_surplus",
            "branch_security_le",
            "branch_security_ge",
            "branch_security_eq",
            "market_node_security_le",
            "market_node_security_ge",
            "market_node_security_eq",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _network(context)
        network = context.artifacts["network_domains"]
        flow = context.artifacts["branch_flow"]
        generation = context.artifacts["generation"]
        purchase = context.artifacts["purchase"]
        block = pyo.Block(concrete=True)
        context.model.add_component("NetworkSecurity", block)
        block.DeficitBranchSecurityConstraint = pyo.Var(
            network.BranchConstraint, domain=pyo.NonNegativeReals
        )
        block.SurplusBranchSecurityConstraint = pyo.Var(
            network.BranchConstraint, domain=pyo.NonNegativeReals
        )
        block.DeficitMNodeConstraint = pyo.Var(
            network.MarketNodeConstraint, domain=pyo.NonNegativeReals
        )
        block.SurplusMNodeConstraint = pyo.Var(
            network.MarketNodeConstraint, domain=pyo.NonNegativeReals
        )

        def branch_expression(key: tuple[str, str, str]) -> Any:
            ca, dt, constraint = key
            return sum(
                data.branch_constraint_factor.get(
                    (ca, dt, constraint, branch), 0.0
                )
                * flow[ca, dt, branch]
                for b_ca, b_dt, branch in data.ac_branches
                if (b_ca, b_dt) == (ca, dt)
            )

        block.BranchSecurityConstraintLE = pyo.Constraint(
            network.BranchConstraint,
            rule=lambda _b, ca, dt, constraint: (
                branch_expression((ca, dt, constraint))
                - _b.SurplusBranchSecurityConstraint[ca, dt, constraint]
                <= data.branch_constraint_limit[ca, dt, constraint]
                if data.branch_constraint_sense[ca, dt, constraint] == -1.0
                else pyo.Constraint.Skip
            ),
        )
        block.BranchSecurityConstraintGE = pyo.Constraint(
            network.BranchConstraint,
            rule=lambda _b, ca, dt, constraint: (
                branch_expression((ca, dt, constraint))
                + _b.DeficitBranchSecurityConstraint[ca, dt, constraint]
                >= data.branch_constraint_limit[ca, dt, constraint]
                if data.branch_constraint_sense[ca, dt, constraint] == 1.0
                else pyo.Constraint.Skip
            ),
        )
        block.BranchSecurityConstraintEQ = pyo.Constraint(
            network.BranchConstraint,
            rule=lambda _b, ca, dt, constraint: (
                branch_expression((ca, dt, constraint))
                + _b.DeficitBranchSecurityConstraint[ca, dt, constraint]
                - _b.SurplusBranchSecurityConstraint[ca, dt, constraint]
                == data.branch_constraint_limit[ca, dt, constraint]
                if data.branch_constraint_sense[ca, dt, constraint] == 0.0
                else pyo.Constraint.Skip
            ),
        )

        def market_expression(key: tuple[str, str, str]) -> Any:
            ca, dt, constraint = key
            return sum(
                data.market_node_energy_offer_factor.get(
                    (ca, dt, constraint, offer), 0.0
                )
                * generation[ca, dt, offer]
                for o_ca, o_dt, offer in data.positive_offers
                if (o_ca, o_dt) == (ca, dt)
            ) + sum(
                data.market_node_energy_bid_factor.get(
                    (ca, dt, constraint, bid), 0.0
                )
                * purchase[ca, dt, bid]
                for b_ca, b_dt, bid in _case(context).bids
                if (b_ca, b_dt) == (ca, dt)
            )

        block.MNodeSecurityConstraintLE = pyo.Constraint(
            network.MarketNodeConstraint,
            rule=lambda _b, ca, dt, constraint: (
                market_expression((ca, dt, constraint))
                - _b.SurplusMNodeConstraint[ca, dt, constraint]
                <= data.market_node_constraint_limit[ca, dt, constraint]
                if data.market_node_constraint_sense[ca, dt, constraint] == -1.0
                else pyo.Constraint.Skip
            ),
        )
        block.MNodeSecurityConstraintGE = pyo.Constraint(
            network.MarketNodeConstraint,
            rule=lambda _b, ca, dt, constraint: (
                market_expression((ca, dt, constraint))
                + _b.DeficitMNodeConstraint[ca, dt, constraint]
                >= data.market_node_constraint_limit[ca, dt, constraint]
                if data.market_node_constraint_sense[ca, dt, constraint] == 1.0
                else pyo.Constraint.Skip
            ),
        )
        block.MNodeSecurityConstraintEQ = pyo.Constraint(
            network.MarketNodeConstraint,
            rule=lambda _b, ca, dt, constraint: (
                market_expression((ca, dt, constraint))
                + _b.DeficitMNodeConstraint[ca, dt, constraint]
                - _b.SurplusMNodeConstraint[ca, dt, constraint]
                == data.market_node_constraint_limit[ca, dt, constraint]
                if data.market_node_constraint_sense[ca, dt, constraint] == 0.0
                else pyo.Constraint.Skip
            ),
        )
        return {
            "branch_constraint_deficit": block.DeficitBranchSecurityConstraint,
            "branch_constraint_surplus": block.SurplusBranchSecurityConstraint,
            "market_node_constraint_deficit": block.DeficitMNodeConstraint,
            "market_node_constraint_surplus": block.SurplusMNodeConstraint,
            "branch_security_le": block.BranchSecurityConstraintLE,
            "branch_security_ge": block.BranchSecurityConstraintGE,
            "branch_security_eq": block.BranchSecurityConstraintEQ,
            "market_node_security_le": block.MNodeSecurityConstraintLE,
            "market_node_security_ge": block.MNodeSecurityConstraintGE,
            "market_node_security_eq": block.MNodeSecurityConstraintEQ,
        }


class NetworkEconomicsComponent(ModelComponent):
    name = "network_economics"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "core_data",
            "domains",
            "network_data",
            "network_domains",
            "generation_block",
            "purchase_block",
            "balance_deficit",
            "balance_surplus",
            "branch_flow_surplus",
            "branch_constraint_deficit",
            "branch_constraint_surplus",
            "market_node_constraint_deficit",
            "market_node_constraint_surplus",
            "ramp_deficit",
            "ramp_surplus",
            "generation_up_delta",
            "generation_down_delta",
            "energy_scarcity_block",
        }
    )
    provides = frozenset(
        {
            "system_cost",
            "system_benefit",
            "balance_penalty",
            "ramp_penalty",
            "movement_cost",
            "scarcity_cost",
            "system_penalty",
            "system_cost_definition",
            "system_benefit_definition",
            "system_penalty_definition",
            "total_violation_definition",
            "total_scarcity_definition",
            "net_benefit",
            "objective",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        data = _network(context)
        domains = context.artifacts["domains"]
        network = context.artifacts["network_domains"]
        generation_block = context.artifacts["generation_block"]
        purchase_block = context.artifacts["purchase_block"]
        deficit = context.artifacts["balance_deficit"]
        surplus = context.artifacts["balance_surplus"]
        branch_surplus = context.artifacts["branch_flow_surplus"]
        branch_deficit = context.artifacts["branch_constraint_deficit"]
        branch_constraint_surplus = context.artifacts["branch_constraint_surplus"]
        market_deficit = context.artifacts["market_node_constraint_deficit"]
        market_surplus = context.artifacts["market_node_constraint_surplus"]
        ramp_deficit = context.artifacts["ramp_deficit"]
        ramp_surplus = context.artifacts["ramp_surplus"]
        up_delta = context.artifacts["generation_up_delta"]
        down_delta = context.artifacts["generation_down_delta"]
        scarcity_block = context.artifacts["energy_scarcity_block"]
        block = pyo.Block(concrete=True)
        context.model.add_component("Economics", block)
        block.SystemCostByPeriod = pyo.Var(domains.Period, domain=pyo.NonNegativeReals)
        block.SystemBenefitByPeriod = pyo.Var(
            domains.Period, domain=pyo.NonNegativeReals
        )
        block.SystemPenaltyByPeriod = pyo.Var(
            domains.Period, domain=pyo.NonNegativeReals
        )
        block.ScarcityCostByPeriod = pyo.Var(
            domains.Period, domain=pyo.NonNegativeReals
        )
        block.TotalPenaltyCost = pyo.Var(domain=pyo.NonNegativeReals)
        block.SystemCostDefinition = pyo.Constraint(
            domains.Period,
            rule=lambda _b, ca, dt: _b.SystemCostByPeriod[ca, dt]
            == sum(
                generation_block[key] * case.offer_price[key]
                for key in domains.OfferBlock
                if key[:2] == (ca, dt)
            ),
        )
        block.SystemBenefitDefinition = pyo.Constraint(
            domains.Period,
            rule=lambda _b, ca, dt: _b.SystemBenefitByPeriod[ca, dt]
            == sum(
                purchase_block[key] * case.bid_price[key]
                for key in domains.BidBlock
                if key[:2] == (ca, dt)
            ),
        )

        def penalty(_b: pyo.Block, ca: str, dt: str) -> Any:
            return _b.SystemPenaltyByPeriod[ca, dt] == (
                sum(
                    data.bus_deficit_penalty * deficit[key]
                    + data.bus_surplus_penalty * surplus[key]
                    for key in network.Bus
                    if key[:2] == (ca, dt)
                )
                + sum(
                    data.branch_flow_surplus_penalty * branch_surplus[key]
                    for key in network.Branch
                    if key[:2] == (ca, dt)
                )
                + sum(
                    case.ramp_deficit_penalty * ramp_deficit[key]
                    + case.ramp_surplus_penalty * ramp_surplus[key]
                    for key in domains.Offer
                    if key[:2] == (ca, dt)
                )
                + sum(
                    data.branch_constraint_deficit_penalty * branch_deficit[key]
                    + data.branch_constraint_surplus_penalty
                    * branch_constraint_surplus[key]
                    for key in network.BranchConstraint
                    if key[:2] == (ca, dt)
                )
                + sum(
                    data.market_node_deficit_penalty * market_deficit[key]
                    + data.market_node_surplus_penalty * market_surplus[key]
                    for key in network.MarketNodeConstraint
                    if key[:2] == (ca, dt)
                )
                + case.movement_penalty
                * sum(
                    up_delta[key] + down_delta[key]
                    for key in domains.RtdOffer
                    if key[:2] == (ca, dt)
                )
            )

        block.SystemPenaltyDefinition = pyo.Constraint(
            domains.Period, rule=penalty
        )
        block.TotalViolationCostDefinition = pyo.Constraint(
            expr=block.TotalPenaltyCost
            == sum(block.SystemPenaltyByPeriod[key] for key in domains.Period)
        )
        block.TotalScarcityCostDefinition = pyo.Constraint(
            domains.Period,
            rule=lambda _b, ca, dt: _b.ScarcityCostByPeriod[ca, dt]
            == sum(
                scarcity_block[key] * case.scarcity_price[key]
                for key in domains.ScarcityBlock
                if key[:2] == (ca, dt)
            ),
        )
        block.SystemCost = pyo.Expression(
            expr=sum(block.SystemCostByPeriod[key] for key in domains.Period)
        )
        block.SystemBenefit = pyo.Expression(
            expr=sum(block.SystemBenefitByPeriod[key] for key in domains.Period)
        )
        block.BalancePenalty = pyo.Expression(
            expr=sum(
                data.bus_deficit_penalty * deficit[key]
                + data.bus_surplus_penalty * surplus[key]
                for key in network.Bus
            )
        )
        block.RampPenalty = pyo.Expression(
            expr=sum(
                case.ramp_deficit_penalty * ramp_deficit[key]
                + case.ramp_surplus_penalty * ramp_surplus[key]
                for key in domains.Offer
            )
        )
        block.MovementCost = pyo.Expression(
            expr=case.movement_penalty
            * sum(up_delta[key] + down_delta[key] for key in domains.RtdOffer)
        )
        block.ScarcityCost = pyo.Expression(
            expr=sum(block.ScarcityCostByPeriod[key] for key in domains.Period)
        )
        block.SystemPenalty = pyo.Expression(
            expr=sum(block.SystemPenaltyByPeriod[key] for key in domains.Period)
        )
        block.NetBenefit = pyo.Expression(
            expr=block.SystemBenefit
            - block.SystemCost
            - block.SystemPenalty
            - block.ScarcityCost
            + sum(
                case.scarcity_limit[key] * case.scarcity_price[key]
                for key in domains.ScarcityBlock
            )
        )
        block.Objective = pyo.Objective(expr=block.NetBenefit, sense=pyo.maximize)
        return {
            "system_cost": block.SystemCost,
            "system_benefit": block.SystemBenefit,
            "balance_penalty": block.BalancePenalty,
            "ramp_penalty": block.RampPenalty,
            "movement_cost": block.MovementCost,
            "scarcity_cost": block.ScarcityCost,
            "system_penalty": block.SystemPenalty,
            "system_cost_definition": block.SystemCostDefinition,
            "system_benefit_definition": block.SystemBenefitDefinition,
            "system_penalty_definition": block.SystemPenaltyDefinition,
            "total_violation_definition": block.TotalViolationCostDefinition,
            "total_scarcity_definition": block.TotalScarcityCostDefinition,
            "net_benefit": block.NetBenefit,
            "objective": block.Objective,
        }
