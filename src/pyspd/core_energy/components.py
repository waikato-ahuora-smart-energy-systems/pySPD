"""Class-based Pyomo components for the core energy-market LP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuildContext, ModelComponent
from pyspd.core_energy.data import CORE_ENERGY_FORMULATION_ID, CoreEnergyCase

_SUPPORTED = frozenset(
    {
        CORE_ENERGY_FORMULATION_ID,
        "vspd-v5.0.6-ac-network",
        "vspd-v5.0.6-hvdc",
        "vspd-v5.0.6-reserve",
        "spd-v16.0-reserve",
    }
)


def _data(context: BuildContext) -> CoreEnergyCase:
    if not isinstance(context.case_data, CoreEnergyCase):
        raise TypeError("core-energy components require CoreEnergyCase")
    return context.case_data


class CoreDomainsComponent(ModelComponent):
    name = "core_domains"
    supported_formulations = _SUPPORTED
    provides = frozenset({"core_data", "domains"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        block = pyo.Block(concrete=True)
        context.model.add_component("CoreDomains", block)
        block.Period = pyo.Set(dimen=2, ordered=True, initialize=sorted(data.periods))
        block.Region = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.regions))
        block.Offer = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.offers))
        block.GenerationOffer = pyo.Set(
            dimen=3, ordered=True, initialize=sorted(data.generation_offers)
        )
        block.OfferBlock = pyo.Set(
            dimen=4, ordered=True, initialize=sorted(data.offer_blocks)
        )
        block.Bid = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.bids))
        block.BidBlock = pyo.Set(
            dimen=4, ordered=True, initialize=sorted(data.bid_blocks)
        )
        block.Node = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.nodes))
        block.ScarcityBlock = pyo.Set(
            dimen=4, ordered=True, initialize=sorted(data.scarcity_blocks)
        )
        block.RampOffer = pyo.Set(
            dimen=3,
            ordered=True,
            initialize=sorted(
                offer
                for offer in data.primary_offers
                if any(key[:3] == offer for key in data.offer_blocks)
            ),
        )
        block.RtdOffer = pyo.Set(
            dimen=3,
            ordered=True,
            initialize=sorted(
                offer
                for offer in data.offers
                if data.study_mode[offer[:2]] in {101.0, 201.0}
            ),
        )
        block.RtdGenerationOffer = pyo.Set(
            dimen=3,
            ordered=True,
            initialize=sorted(
                offer
                for offer in data.generation_offers
                if data.study_mode[offer[:2]] in {101.0, 201.0}
            ),
        )
        context.model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
        return {"core_data": data, "domains": block}


class EnergyOffersComponent(ModelComponent):
    name = "energy_offers"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains"})
    provides = frozenset({"generation", "generation_block", "generation_definition"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["domains"]
        block = pyo.Block(concrete=True)
        context.model.add_component("EnergyOffers", block)
        block.GenerationBlock = pyo.Var(
            domains.OfferBlock,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, offer, tranche: (
                0.0,
                data.offer_limit[(ca, dt, offer, tranche)],
            ),
        )
        block.Generation = pyo.Var(
            domains.GenerationOffer,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, offer: (
                0.0,
                (
                    None
                    if (ca, dt, offer) not in data.offers
                    else data.generation_maximum.get((ca, dt, offer))
                    if any(key[:3] == (ca, dt, offer) for key in data.offer_blocks)
                    else 0.0
                ),
            ),
        )

        def generation_definition(
            _block: pyo.Block, ca: str, dt: str, offer: str
        ) -> pyo.Constraint:
            return _block.Generation[ca, dt, offer] == sum(
                _block.GenerationBlock[key]
                for key in domains.OfferBlock
                if key[:3] == (ca, dt, offer)
            )

        block.GenerationOfferDefinition = pyo.Constraint(
            domains.Offer, rule=generation_definition
        )
        return {
            "generation": block.Generation,
            "generation_block": block.GenerationBlock,
            "generation_definition": block.GenerationOfferDefinition,
        }


class DemandBidsComponent(ModelComponent):
    name = "demand_bids"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains"})
    provides = frozenset({"purchase", "purchase_block", "purchase_definition"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["domains"]
        block = pyo.Block(concrete=True)
        context.model.add_component("DemandBids", block)

        def bid_bounds(
            _block: pyo.Block, ca: str, dt: str, bid: str, tranche: str
        ) -> tuple[float | None, float | None]:
            limit = data.bid_limit[(ca, dt, bid, tranche)]
            return (0.0, limit) if limit >= 0.0 else (limit, 0.0)

        block.PurchaseBlock = pyo.Var(
            domains.BidBlock, domain=pyo.Reals, bounds=bid_bounds
        )
        block.Purchase = pyo.Var(domains.Bid, domain=pyo.Reals)

        def purchase_definition(
            _block: pyo.Block, ca: str, dt: str, bid: str
        ) -> pyo.Constraint:
            return _block.Purchase[ca, dt, bid] == sum(
                _block.PurchaseBlock[key]
                for key in domains.BidBlock
                if key[:3] == (ca, dt, bid)
            )

        block.DemandBidDefinition = pyo.Constraint(
            domains.Bid, rule=purchase_definition
        )
        return {
            "purchase": block.Purchase,
            "purchase_block": block.PurchaseBlock,
            "purchase_definition": block.DemandBidDefinition,
        }


class EnergyBalanceComponent(ModelComponent):
    name = "energy_balance"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "core_data",
            "domains",
            "generation",
            "purchase",
            "energy_scarcity_node",
        }
    )
    provides = frozenset({"balance_deficit", "balance_surplus", "energy_balance"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["domains"]
        generation = context.artifacts["generation"]
        purchase = context.artifacts["purchase"]
        scarcity = context.artifacts["energy_scarcity_node"]
        block = pyo.Block(concrete=True)
        context.model.add_component("EnergyBalance", block)
        block.DeficitGeneration = pyo.Var(domains.Region, domain=pyo.NonNegativeReals)
        block.SurplusGeneration = pyo.Var(domains.Region, domain=pyo.NonNegativeReals)

        def balance(_block: pyo.Block, ca: str, dt: str, island: str) -> pyo.Constraint:
            region = (ca, dt, island)
            supply = sum(
                generation[offer]
                for offer in domains.Offer
                if data.offer_region[offer] == region
            )
            dispatchable_load = sum(
                purchase[bid] for bid in domains.Bid if data.bid_region[bid] == region
            )
            scarcity_supply = sum(
                scarcity[node]
                for node in domains.Node
                if data.node_region[node] == region
            )
            return (
                supply + scarcity_supply + _block.DeficitGeneration[region]
                == data.required_load[region]
                + dispatchable_load
                + _block.SurplusGeneration[region]
            )

        block.Balance = pyo.Constraint(domains.Region, rule=balance)
        return {
            "balance_deficit": block.DeficitGeneration,
            "balance_surplus": block.SurplusGeneration,
            "energy_balance": block.Balance,
        }


class EnergyScarcityComponent(ModelComponent):
    name = "energy_scarcity"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains"})
    provides = frozenset(
        {
            "energy_scarcity_block",
            "energy_scarcity_node",
            "energy_scarcity_definition",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["domains"]
        block = pyo.Block(concrete=True)
        context.model.add_component("EnergyScarcity", block)
        block.EnergyScarcityBlock = pyo.Var(
            domains.ScarcityBlock,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, node, tranche: (
                0.0,
                data.scarcity_limit[(ca, dt, node, tranche)]
                if data.scarcity_enabled[(ca, dt)] != 0.0
                else 0.0,
            ),
        )
        block.EnergyScarcityNode = pyo.Var(domains.Node, domain=pyo.NonNegativeReals)
        block.EnergyScarcityDefinition = pyo.Constraint(
            domains.Node,
            rule=lambda _b, ca, dt, node: (
                _b.EnergyScarcityNode[ca, dt, node]
                == sum(
                    _b.EnergyScarcityBlock[key]
                    for key in domains.ScarcityBlock
                    if key[:3] == (ca, dt, node)
                )
            ),
        )
        return {
            "energy_scarcity_block": block.EnergyScarcityBlock,
            "energy_scarcity_node": block.EnergyScarcityNode,
            "energy_scarcity_definition": block.EnergyScarcityDefinition,
        }


class GenerationRampingComponent(ModelComponent):
    name = "generation_ramping"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains", "generation"})
    provides = frozenset(
        {
            "generation_up_delta",
            "generation_down_delta",
            "generation_change",
            "ramp_deficit",
            "ramp_surplus",
            "ramp_up",
            "ramp_down",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["domains"]
        generation = context.artifacts["generation"]
        block = pyo.Block(concrete=True)
        context.model.add_component("GenerationRamping", block)
        block.GenerationUpDelta = pyo.Var(
            domains.GenerationOffer, domain=pyo.NonNegativeReals
        )
        block.GenerationDownDelta = pyo.Var(
            domains.GenerationOffer, domain=pyo.NonNegativeReals
        )
        block.DeficitRampRate = pyo.Var(domains.Offer, domain=pyo.NonNegativeReals)
        block.SurplusRampRate = pyo.Var(domains.Offer, domain=pyo.NonNegativeReals)

        block.GenerationChange = pyo.Constraint(
            domains.RtdGenerationOffer,
            rule=lambda _b, ca, dt, offer: (
                _b.GenerationUpDelta[ca, dt, offer]
                - _b.GenerationDownDelta[ca, dt, offer]
                == generation[ca, dt, offer] - data.generation_start[(ca, dt, offer)]
            ),
        )

        def total_generation(offer: tuple[str, str, str]) -> Any:
            secondary = (
                (map_ca, map_dt, child)
                for map_ca, map_dt, parent, child in data.primary_secondary
                if (map_ca, map_dt, parent) == offer
            )
            return generation[offer] + sum(generation[item] for item in secondary)

        block.RampUp = pyo.Constraint(
            domains.RampOffer,
            rule=lambda _b, ca, dt, offer: (
                total_generation((ca, dt, offer)) - _b.DeficitRampRate[ca, dt, offer]
                <= data.generation_start[(ca, dt, offer)]
                + data.ramp_rate_up[(ca, dt, offer)]
                * data.interval_minutes[(ca, dt)]
                / 60.0
            ),
        )
        block.RampDown = pyo.Constraint(
            domains.RampOffer,
            rule=lambda _b, ca, dt, offer: (
                total_generation((ca, dt, offer)) + _b.SurplusRampRate[ca, dt, offer]
                >= data.generation_start[(ca, dt, offer)]
                - data.ramp_rate_down[(ca, dt, offer)]
                * data.interval_minutes[(ca, dt)]
                / 60.0
            ),
        )
        return {
            "generation_up_delta": block.GenerationUpDelta,
            "generation_down_delta": block.GenerationDownDelta,
            "generation_change": block.GenerationChange,
            "ramp_deficit": block.DeficitRampRate,
            "ramp_surplus": block.SurplusRampRate,
            "ramp_up": block.RampUp,
            "ramp_down": block.RampDown,
        }


class CoreEconomicsComponent(ModelComponent):
    name = "core_economics"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "core_data",
            "domains",
            "generation_block",
            "purchase_block",
            "balance_deficit",
            "balance_surplus",
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
        data = _data(context)
        domains = context.artifacts["domains"]
        generation_block = context.artifacts["generation_block"]
        purchase_block = context.artifacts["purchase_block"]
        deficit = context.artifacts["balance_deficit"]
        surplus = context.artifacts["balance_surplus"]
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
            rule=lambda _b, ca, dt: (
                _b.SystemCostByPeriod[ca, dt]
                == sum(
                    generation_block[key] * data.offer_price[key]
                    for key in domains.OfferBlock
                    if key[:2] == (ca, dt)
                )
            ),
        )
        block.SystemBenefitDefinition = pyo.Constraint(
            domains.Period,
            rule=lambda _b, ca, dt: (
                _b.SystemBenefitByPeriod[ca, dt]
                == sum(
                    purchase_block[key] * data.bid_price[key]
                    for key in domains.BidBlock
                    if key[:2] == (ca, dt)
                )
            ),
        )
        block.SystemPenaltyDefinition = pyo.Constraint(
            domains.Period,
            rule=lambda _b, ca, dt: (
                _b.SystemPenaltyByPeriod[ca, dt]
                == sum(
                    data.balance_deficit_penalty * deficit[key]
                    + data.balance_surplus_penalty * surplus[key]
                    for key in domains.Region
                    if key[:2] == (ca, dt)
                )
                + sum(
                    data.ramp_deficit_penalty * ramp_deficit[key]
                    + data.ramp_surplus_penalty * ramp_surplus[key]
                    for key in domains.Offer
                    if key[:2] == (ca, dt)
                )
                + data.movement_penalty
                * sum(
                    up_delta[key] + down_delta[key]
                    for key in domains.RtdGenerationOffer
                    if key[:2] == (ca, dt)
                )
            ),
        )
        block.TotalViolationCostDefinition = pyo.Constraint(
            expr=block.TotalPenaltyCost
            == sum(block.SystemPenaltyByPeriod[key] for key in domains.Period)
        )
        block.TotalScarcityCostDefinition = pyo.Constraint(
            domains.Period,
            rule=lambda _b, ca, dt: (
                _b.ScarcityCostByPeriod[ca, dt]
                == sum(
                    scarcity_block[key] * data.scarcity_price[key]
                    for key in domains.ScarcityBlock
                    if key[:2] == (ca, dt)
                )
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
                data.balance_deficit_penalty * deficit[key]
                + data.balance_surplus_penalty * surplus[key]
                for key in domains.Region
            )
        )
        block.RampPenalty = pyo.Expression(
            expr=sum(
                data.ramp_deficit_penalty * ramp_deficit[key]
                + data.ramp_surplus_penalty * ramp_surplus[key]
                for key in domains.Offer
            )
        )
        block.MovementCost = pyo.Expression(
            expr=data.movement_penalty
            * sum(up_delta[key] + down_delta[key] for key in domains.RtdGenerationOffer)
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
                data.scarcity_limit[key] * data.scarcity_price[key]
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
