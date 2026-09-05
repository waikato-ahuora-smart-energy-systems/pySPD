"""Class-based HVDC, portable SOS, discrete-bid, and coupling components."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import pairwise
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuildContext, ModelComponent
from pyspd.hvdc.data import (
    HVDC_FORMULATION_ID,
    HvdcCase,
    HvdcData,
    SosRepresentation,
)
from pyspd.network.components import (
    ACNetworkComponent,
    NetworkBuildIndex,
    NetworkEconomicsComponent,
    NetworkSecurityComponent,
)
from pyspd.network.data import NetworkData

type Key = tuple[str, ...]

_SUPPORTED = frozenset(
    {HVDC_FORMULATION_ID, "vspd-v5.0.6-reserve", "spd-v16.0-reserve"}
)


def _case(context: BuildContext) -> HvdcCase:
    if not isinstance(context.case_data, HvdcCase):
        raise TypeError("HVDC components require HvdcCase")
    return context.case_data


def _hvdc(context: BuildContext) -> HvdcData:
    data = _case(context).hvdc
    assert data is not None
    return data


def _network(context: BuildContext) -> NetworkData:
    data = _case(context).network
    assert data is not None
    return data


class HVDCDomainsComponent(ModelComponent):
    name = "hvdc_domains"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains", "network_data", "network_domains"})
    provides = frozenset({"hvdc_data", "hvdc_domains"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _hvdc(context)
        block = pyo.Block(concrete=True)
        context.model.add_component("HVDCDomains", block)
        block.HVDCLink = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.links))
        block.Breakpoint = pyo.Set(
            dimen=4, ordered=True, initialize=sorted(data.breakpoints)
        )
        intervals: list[Key] = []
        for link in sorted(data.links):
            ordered = sorted(
                (data.breakpoint_order[key], key)
                for key in data.breakpoints
                if key[:3] == link
            )
            intervals.extend(
                (*link, left[3]) for (_order, left), _right in pairwise(ordered)
            )
        block.SOSInterval = pyo.Set(dimen=4, ordered=True, initialize=sorted(intervals))
        block.FlowDirection = pyo.Set(
            dimen=3,
            ordered=True,
            initialize=sorted(
                (*period, direction)
                for period in _case(context).periods
                for direction in ("forward", "backward")
            ),
        )
        block.DiscreteBidBlock = pyo.Set(
            dimen=4,
            ordered=True,
            initialize=sorted(data.discrete_bid_blocks),
        )
        return {"hvdc_data": data, "hvdc_domains": block}


class HVDCTransmissionComponent(ModelComponent):
    name = "hvdc_transmission"
    supported_formulations = _SUPPORTED
    requires = frozenset({"hvdc_data", "hvdc_domains"})
    provides = frozenset(
        {
            "hvdc_flow",
            "hvdc_loss",
            "hvdc_lambda",
            "hvdc_sos_binary",
            "hvdc_direction_binary",
            "hvdc_maximum_flow",
            "hvdc_loss_definition",
            "hvdc_flow_definition",
            "hvdc_lambda_definition",
            "hvdc_sos_constraints",
            "hvdc_direction_constraints",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _hvdc(context)
        domains = context.artifacts["hvdc_domains"]
        block = pyo.Block(concrete=True)
        context.model.add_component("HVDCTransmission", block)
        block.HVDCLinkFlow = pyo.Var(domains.HVDCLink, domain=pyo.NonNegativeReals)
        block.HVDCLinkLosses = pyo.Var(domains.HVDCLink, domain=pyo.NonNegativeReals)
        block.Lambda = pyo.Var(
            domains.Breakpoint, domain=pyo.NonNegativeReals, bounds=(0.0, 1.0)
        )
        block.HVDCLinkMaximumFlow = pyo.Constraint(
            domains.HVDCLink,
            rule=lambda _b, ca, dt, link: (
                _b.HVDCLinkFlow[ca, dt, link] <= data.capacity[ca, dt, link]
                if data.use_hvdc_branch_limits
                else pyo.Constraint.Skip
            ),
        )
        block.HVDCLinkLossDefinition = pyo.Constraint(
            domains.HVDCLink,
            rule=lambda _b, ca, dt, link: (
                _b.HVDCLinkLosses[ca, dt, link]
                == sum(
                    data.breakpoint_loss[key] * _b.Lambda[key]
                    for key in domains.Breakpoint
                    if key[:3] == (ca, dt, link)
                )
            ),
        )
        block.HVDCLinkFlowDefinition = pyo.Constraint(
            domains.HVDCLink,
            rule=lambda _b, ca, dt, link: (
                _b.HVDCLinkFlow[ca, dt, link]
                == sum(
                    data.breakpoint_flow[key] * _b.Lambda[key]
                    for key in domains.Breakpoint
                    if key[:3] == (ca, dt, link)
                )
            ),
        )
        block.LambdaDefinition = pyo.Constraint(
            domains.HVDCLink,
            rule=lambda _b, ca, dt, link: (
                sum(
                    data.lambda_weight[key] * _b.Lambda[key]
                    for key in domains.Breakpoint
                    if key[:3] == (ca, dt, link)
                )
                == 1.0
            ),
        )

        portable = data.enforce_sos2 and (
            data.sos_representation is SosRepresentation.PORTABLE
        )
        block.SOSIntervalBinary = pyo.Var(
            domains.SOSInterval,
            domain=pyo.Binary if portable else pyo.NonNegativeReals,
            bounds=(0.0, 1.0 if portable else 0.0),
        )
        block.SOSIntervalSelection = pyo.ConstraintList()
        block.SOSAdjacency = pyo.ConstraintList()
        if portable:
            for link in sorted(data.links):
                points = [
                    key
                    for _order, key in sorted(
                        (data.breakpoint_order[key], key)
                        for key in data.breakpoints
                        if key[:3] == link
                    )
                ]
                intervals = [(*link, key[3]) for key in points[:-1]]
                block.SOSIntervalSelection.add(
                    sum(block.SOSIntervalBinary[key] for key in intervals) == 1.0
                )
                block.SOSAdjacency.add(
                    block.Lambda[points[0]] <= block.SOSIntervalBinary[intervals[0]]
                )
                block.SOSAdjacency.add(
                    block.Lambda[points[-1]] <= block.SOSIntervalBinary[intervals[-1]]
                )
                for index, point in enumerate(points[1:-1], start=1):
                    block.SOSAdjacency.add(
                        block.Lambda[point]
                        <= block.SOSIntervalBinary[intervals[index - 1]]
                        + block.SOSIntervalBinary[intervals[index]]
                    )
        if data.enforce_sos2 and data.sos_representation is SosRepresentation.NATIVE:

            def native_sos_rule(_b: pyo.Block, ca: str, dt: str, link: str) -> Any:
                points = [
                    key
                    for _order, key in sorted(
                        (data.breakpoint_order[key], key)
                        for key in data.breakpoints
                        if key[:3] == (ca, dt, link)
                    )
                ]
                return (
                    [block.Lambda[key] for key in points],
                    [data.breakpoint_order[key] for key in points],
                )

            block.NativeSOS2 = pyo.SOSConstraint(
                domains.HVDCLink, rule=native_sos_rule, sos=2
            )

        direction_active = data.enforce_flow_direction
        block.FlowDirectionBinary = pyo.Var(
            domains.FlowDirection,
            domain=pyo.Binary if direction_active else pyo.NonNegativeReals,
            bounds=(0.0, 1.0 if direction_active else 0.0),
        )
        block.OnlyOneFlowDirection = pyo.ConstraintList()
        block.LinkFlowDirectionLimit = pyo.ConstraintList()
        if direction_active:
            for period in sorted(_case(context).periods):
                block.OnlyOneFlowDirection.add(
                    sum(
                        block.FlowDirectionBinary[*period, direction]
                        for direction in ("forward", "backward")
                    )
                    <= 1.0
                )
            for link in sorted(data.links):
                block.LinkFlowDirectionLimit.add(
                    block.HVDCLinkFlow[link]
                    <= data.capacity[link]
                    * block.FlowDirectionBinary[*link[:2], data.link_direction[link]]
                )
        return {
            "hvdc_flow": block.HVDCLinkFlow,
            "hvdc_loss": block.HVDCLinkLosses,
            "hvdc_lambda": block.Lambda,
            "hvdc_sos_binary": block.SOSIntervalBinary,
            "hvdc_direction_binary": block.FlowDirectionBinary,
            "hvdc_maximum_flow": block.HVDCLinkMaximumFlow,
            "hvdc_loss_definition": block.HVDCLinkLossDefinition,
            "hvdc_flow_definition": block.HVDCLinkFlowDefinition,
            "hvdc_lambda_definition": block.LambdaDefinition,
            "hvdc_sos_constraints": (
                block.NativeSOS2
                if hasattr(block, "NativeSOS2")
                else (block.SOSIntervalSelection, block.SOSAdjacency)
            ),
            "hvdc_direction_constraints": (
                block.OnlyOneFlowDirection,
                block.LinkFlowDirectionLimit,
            ),
        }


class DiscreteDemandComponent(ModelComponent):
    name = "discrete_demand"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "hvdc_data", "hvdc_domains", "purchase_block"})
    provides = frozenset({"purchase_block_binary", "discrete_bid_definition"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        domains = context.artifacts["hvdc_domains"]
        purchase_block = context.artifacts["purchase_block"]
        block = pyo.Block(concrete=True)
        context.model.add_component("DiscreteDemand", block)
        block.PurchaseBlockBinary = pyo.Var(domains.DiscreteBidBlock, domain=pyo.Binary)
        block.DemBidDiscrete = pyo.Constraint(
            domains.DiscreteBidBlock,
            rule=lambda _b, ca, dt, bid, tranche: (
                purchase_block[ca, dt, bid, tranche]
                == _b.PurchaseBlockBinary[ca, dt, bid, tranche]
                * case.bid_limit[ca, dt, bid, tranche]
            ),
        )
        return {
            "purchase_block_binary": block.PurchaseBlockBinary,
            "discrete_bid_definition": block.DemBidDiscrete,
        }


class HVDCACNetworkComponent(ACNetworkComponent):
    name = "ac_network"
    supported_formulations = _SUPPORTED
    requires = ACNetworkComponent.requires | frozenset(
        {"hvdc_data", "hvdc_domains", "hvdc_flow", "hvdc_loss"}
    )

    def _energy_balance(
        self,
        context: BuildContext,
        block: pyo.Block,
        build_index: NetworkBuildIndex,
    ) -> pyo.Constraint:
        network_data = _network(context)
        hvdc_data = _hvdc(context)
        network = context.artifacts["network_domains"]
        generation = context.artifacts["generation"]
        purchase = context.artifacts["purchase"]
        scarcity = context.artifacts["energy_scarcity_node"]
        hvdc_flow = context.artifacts["hvdc_flow"]
        hvdc_loss = context.artifacts["hvdc_loss"]
        received_links: dict[Key, list[Key]] = {}
        sent_links: dict[Key, list[Key]] = {}
        for link in sorted(hvdc_data.links):
            for bus_key in sorted(network_data.buses):
                if link[:2] != bus_key[:2]:
                    continue
                if (*link, bus_key[2]) in hvdc_data.receiving_bus:
                    received_links.setdefault(bus_key, []).append(link)
                if (*link, bus_key[2]) in hvdc_data.sending_bus:
                    sent_links.setdefault(bus_key, []).append(link)

        def bus_balance(_b: pyo.Block, ca: str, dt: str, bus: str) -> Any:
            bus_key = (ca, dt, bus)
            supply = sum(
                network_data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * generation[offer]
                for offer, node in build_index.offers.get(bus_key, ())
            )
            demand_bid = sum(
                network_data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * purchase[bid]
                for bid, node in build_index.bids.get(bus_key, ())
            )
            load = sum(
                network_data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * network_data.node_load[(ca, dt, node)]
                for node in build_index.nodes.get(bus_key, ())
            )
            ac_loss = sum(
                (
                    network_data.receiving_end_loss_proportion
                    if is_receiving
                    else 1.0 - network_data.receiving_end_loss_proportion
                )
                * _b.ACBranchLossesDirected[*branch, direction]
                for branch, direction, is_receiving in build_index.incident.get(
                    bus_key, ()
                )
            )
            fixed_loss = sum(
                0.5 * network_data.branch_fixed_loss[branch]
                for branch in build_index.fixed_loss_branches.get(bus_key, ())
            )
            received_hvdc = sum(
                hvdc_flow[link] - hvdc_loss[link]
                for link in received_links.get(bus_key, ())
            )
            sent_hvdc = sum(hvdc_flow[link] for link in sent_links.get(bus_key, ()))
            scarcity_supply = sum(
                network_data.node_bus_allocation.get((ca, dt, node, bus), 0.0)
                * scarcity[ca, dt, node]
                for node in build_index.nodes.get(bus_key, ())
            )
            return _b.ACNodeNetInjection[bus_key] == (
                supply
                - demand_bid
                - load
                + received_hvdc
                - sent_hvdc
                - ac_loss
                - fixed_loss
                + _b.DeficitBusGeneration[bus_key]
                - _b.SurplusBusGeneration[bus_key]
                + scarcity_supply
            )

        return pyo.Constraint(network.Bus, rule=bus_balance)


class HVDCSecurityComponent(NetworkSecurityComponent):
    name = "network_security"
    supported_formulations = _SUPPORTED
    requires = NetworkSecurityComponent.requires | frozenset({"hvdc_data", "hvdc_flow"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        artifacts = dict(super().build(context))
        data = _network(context)
        hvdc_data = _hvdc(context)
        domains = context.artifacts["network_domains"]
        ac_flow = context.artifacts["branch_flow"]
        hvdc_flow = context.artifacts["hvdc_flow"]
        block = context.model.NetworkSecurity
        for name in (
            "BranchSecurityConstraintLE",
            "BranchSecurityConstraintGE",
            "BranchSecurityConstraintEQ",
        ):
            block.del_component(getattr(block, name))

        def expression(key: Key) -> Any:
            ca, dt, constraint = key
            return sum(
                data.branch_constraint_factor.get((ca, dt, constraint, branch), 0.0)
                * ac_flow[ca, dt, branch]
                for b_ca, b_dt, branch in data.ac_branches
                if (b_ca, b_dt) == (ca, dt)
            ) + sum(
                data.branch_constraint_factor.get((ca, dt, constraint, link), 0.0)
                * hvdc_flow[ca, dt, link]
                for h_ca, h_dt, link in hvdc_data.links
                if (h_ca, h_dt) == (ca, dt)
            )

        block.BranchSecurityConstraintLE = pyo.Constraint(
            domains.BranchConstraint,
            rule=lambda _b, ca, dt, constraint: (
                expression((ca, dt, constraint))
                - _b.SurplusBranchSecurityConstraint[ca, dt, constraint]
                <= data.branch_constraint_limit[ca, dt, constraint]
                if data.branch_constraint_sense[ca, dt, constraint] == -1.0
                else pyo.Constraint.Skip
            ),
        )
        block.BranchSecurityConstraintGE = pyo.Constraint(
            domains.BranchConstraint,
            rule=lambda _b, ca, dt, constraint: (
                expression((ca, dt, constraint))
                + _b.DeficitBranchSecurityConstraint[ca, dt, constraint]
                >= data.branch_constraint_limit[ca, dt, constraint]
                if data.branch_constraint_sense[ca, dt, constraint] == 1.0
                else pyo.Constraint.Skip
            ),
        )
        block.BranchSecurityConstraintEQ = pyo.Constraint(
            domains.BranchConstraint,
            rule=lambda _b, ca, dt, constraint: (
                expression((ca, dt, constraint))
                + _b.DeficitBranchSecurityConstraint[ca, dt, constraint]
                - _b.SurplusBranchSecurityConstraint[ca, dt, constraint]
                == data.branch_constraint_limit[ca, dt, constraint]
                if data.branch_constraint_sense[ca, dt, constraint] == 0.0
                else pyo.Constraint.Skip
            ),
        )
        artifacts["branch_security_le"] = block.BranchSecurityConstraintLE
        artifacts["branch_security_ge"] = block.BranchSecurityConstraintGE
        artifacts["branch_security_eq"] = block.BranchSecurityConstraintEQ
        return artifacts


class HVDCEconomicsComponent(NetworkEconomicsComponent):
    name = "network_economics"
    supported_formulations = _SUPPORTED
