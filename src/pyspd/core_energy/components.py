"""Class-based Pyomo components for the core energy-market LP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuildContext, ModelComponent
from pyspd.core_energy.data import CORE_ENERGY_FORMULATION_ID, CoreEnergyCase

_SUPPORTED = frozenset({CORE_ENERGY_FORMULATION_ID})


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
        block.OfferBlock = pyo.Set(
            dimen=4, ordered=True, initialize=sorted(data.offer_blocks)
        )
        block.Bid = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.bids))
        block.BidBlock = pyo.Set(
            dimen=4, ordered=True, initialize=sorted(data.bid_blocks)
        )
        block.RampOffer = pyo.Set(
            dimen=3,
            ordered=True,
            initialize=sorted(
                offer
                for offer in data.primary_offers
                if any(key[:3] == offer for key in data.offer_blocks)
                and data.study_mode[offer[:2]] in {101.0, 201.0}
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
        context.model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
        return {"core_data": data, "domains": block}


class EnergyOffersComponent(ModelComponent):
    name = "energy_offers"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains"})
    provides = frozenset(
        {"generation", "generation_block", "generation_definition"}
    )

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
            domains.Offer,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, offer: (
                0.0,
                data.generation_maximum.get((ca, dt, offer)),
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
        {"core_data", "domains", "generation", "purchase"}
    )
    provides = frozenset(
        {"balance_deficit", "balance_surplus", "energy_balance"}
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["domains"]
        generation = context.artifacts["generation"]
        purchase = context.artifacts["purchase"]
        block = pyo.Block(concrete=True)
        context.model.add_component("EnergyBalance", block)
        block.DeficitGeneration = pyo.Var(domains.Region, domain=pyo.NonNegativeReals)
        block.SurplusGeneration = pyo.Var(domains.Region, domain=pyo.NonNegativeReals)

        def balance(
            _block: pyo.Block, ca: str, dt: str, island: str
        ) -> pyo.Constraint:
            region = (ca, dt, island)
            supply = sum(
                generation[offer]
                for offer in domains.Offer
                if data.offer_region[offer] == region
            )
            dispatchable_load = sum(
                purchase[bid]
                for bid in domains.Bid
                if data.bid_region[bid] == region
            )
            return (
                supply + _block.DeficitGeneration[region]
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
        block.GenerationUpDelta = pyo.Var(domains.RtdOffer, domain=pyo.NonNegativeReals)
        block.GenerationDownDelta = pyo.Var(
            domains.RtdOffer, domain=pyo.NonNegativeReals
        )
        block.DeficitRampRate = pyo.Var(domains.RampOffer, domain=pyo.NonNegativeReals)
        block.SurplusRampRate = pyo.Var(domains.RampOffer, domain=pyo.NonNegativeReals)

        block.GenerationChange = pyo.Constraint(
            domains.RtdOffer,
            rule=lambda _b, ca, dt, offer: (
                _b.GenerationUpDelta[ca, dt, offer]
                - _b.GenerationDownDelta[ca, dt, offer]
                == generation[ca, dt, offer]
                - data.generation_start[(ca, dt, offer)]
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
                total_generation((ca, dt, offer))
                - _b.DeficitRampRate[ca, dt, offer]
                <= data.generation_start[(ca, dt, offer)]
                + data.ramp_rate_up[(ca, dt, offer)]
                * data.interval_minutes[(ca, dt)]
                / 60.0
            ),
        )
        block.RampDown = pyo.Constraint(
            domains.RampOffer,
            rule=lambda _b, ca, dt, offer: (
                total_generation((ca, dt, offer))
                + _b.SurplusRampRate[ca, dt, offer]
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
        }
    )
    provides = frozenset(
        {
            "system_cost",
            "system_benefit",
            "balance_penalty",
            "ramp_penalty",
            "movement_cost",
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
        block = pyo.Block(concrete=True)
        context.model.add_component("Economics", block)
        block.SystemCost = pyo.Expression(
            expr=sum(
                generation_block[key] * data.offer_price[key]
                for key in domains.OfferBlock
            )
        )
        block.SystemBenefit = pyo.Expression(
            expr=sum(
                purchase_block[key] * data.bid_price[key]
                for key in domains.BidBlock
            )
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
                for key in domains.RampOffer
            )
        )
        block.MovementCost = pyo.Expression(
            expr=data.movement_penalty
            * sum(up_delta[key] + down_delta[key] for key in domains.RtdOffer)
        )
        block.NetBenefit = pyo.Expression(
            expr=block.SystemBenefit
            - block.SystemCost
            - block.BalancePenalty
            - block.RampPenalty
            - block.MovementCost
        )
        block.Objective = pyo.Objective(expr=block.NetBenefit, sense=pyo.maximize)
        return {
            "system_cost": block.SystemCost,
            "system_benefit": block.SystemBenefit,
            "balance_penalty": block.BalancePenalty,
            "ramp_penalty": block.RampPenalty,
            "movement_cost": block.MovementCost,
            "net_benefit": block.NetBenefit,
            "objective": block.Objective,
        }
