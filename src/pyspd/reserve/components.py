"""Class-based reserve, risk, NMIR sharing, scarcity, and economics components."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuildContext, ModelComponent
from pyspd.hvdc.components import HVDCEconomicsComponent, HVDCSecurityComponent
from pyspd.hvdc.data import SosRepresentation
from pyspd.reserve.data import (
    BLOCKS,
    DIRECTIONS,
    ENERGY_BREAKPOINTS,
    RESERVE_BREAKPOINTS,
    RESERVE_CLASSES,
    RESERVE_FORMULATION_ID,
    RESERVE_TYPES,
    ZONES,
    ReserveCase,
    ReserveData,
)

type Key = tuple[str, ...]

_SUPPORTED = frozenset({RESERVE_FORMULATION_ID, "spd-v16.0-reserve"})


def _case(context: BuildContext) -> ReserveCase:
    if not isinstance(context.case_data, ReserveCase):
        raise TypeError("reserve components require ReserveCase")
    return context.case_data


def _data(context: BuildContext) -> ReserveData:
    data = _case(context).reserve
    assert data is not None
    return data


class ReserveDomainsComponent(ModelComponent):
    name = "reserve_domains"
    supported_formulations = _SUPPORTED
    requires = frozenset({"core_data", "domains", "hvdc_data", "hvdc_domains"})
    provides = frozenset({"reserve_data", "reserve_domains"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        data = _data(context)
        block = pyo.Block(concrete=True)
        context.model.add_component("ReserveDomains", block)
        block.Island = pyo.Set(dimen=3, ordered=True, initialize=sorted(data.islands))
        block.ReserveClass = pyo.Set(ordered=True, initialize=RESERVE_CLASSES)
        block.ReserveType = pyo.Set(ordered=True, initialize=RESERVE_TYPES)
        block.RiskClass = pyo.Set(ordered=True, initialize=data.risk_classes)
        block.Direction = pyo.Set(ordered=True, initialize=DIRECTIONS)
        block.Zone = pyo.Set(ordered=True, initialize=ZONES)
        block.Block = pyo.Set(ordered=True, initialize=BLOCKS)
        block.EnergyBreakpoint = pyo.Set(ordered=True, initialize=ENERGY_BREAKPOINTS)
        block.ReserveBreakpoint = pyo.Set(ordered=True, initialize=RESERVE_BREAKPOINTS)
        block.ReserveOffer = pyo.Set(
            dimen=5,
            ordered=True,
            initialize=sorted(
                (*offer, reserve_class, reserve_type)
                for offer in case.offers
                for reserve_class in RESERVE_CLASSES
                for reserve_type in RESERVE_TYPES
            ),
        )
        block.ReserveBlock = pyo.Set(
            dimen=6, ordered=True, initialize=sorted(data.reserve_block_limit)
        )
        block.IslandRisk = pyo.Set(
            dimen=5,
            ordered=True,
            initialize=sorted(
                (*island, reserve_class, risk)
                for island in data.islands
                for reserve_class in RESERVE_CLASSES
                for risk in data.risk_classes
            ),
        )
        block.GeneratorRisk = pyo.Set(
            dimen=6,
            ordered=True,
            initialize=sorted(
                (*generator, reserve_class, risk)
                for generator in data.risk_generators
                for reserve_class in RESERVE_CLASSES
                for risk in data.generator_risks
            ),
        )
        block.RiskGroup = pyo.Set(
            dimen=6,
            ordered=True,
            initialize=sorted(
                (group[0], group[1], group[2], group[3], reserve_class, group[4])
                for group in data.island_risk_group
                if group[4] in data.group_risks
                for reserve_class in RESERVE_CLASSES
            ),
        )
        block.Shortfall = pyo.Set(
            dimen=5,
            ordered=True,
            initialize=sorted(
                (*island, reserve_class, risk)
                for island in data.islands
                for reserve_class in RESERVE_CLASSES
                for risk in data.hvdc_risks
                | data.manual_risks
                | data.hvdc_secondary_risks
                if risk in data.ce_risks
            ),
        )
        block.ShortfallUnit = pyo.Set(
            dimen=6,
            ordered=True,
            initialize=sorted(
                (*generator, reserve_class, risk)
                for generator in data.risk_generators
                for reserve_class in RESERVE_CLASSES
                for risk in data.generator_risks | data.hvdc_secondary_risks
                if risk in data.ce_risks
            ),
        )
        block.ShortfallGroup = pyo.Set(
            dimen=6,
            ordered=True,
            initialize=sorted(
                (group[0], group[1], group[2], group[3], reserve_class, group[4])
                for group in data.island_risk_group
                if group[4] in data.ce_risks & data.group_risks
                for reserve_class in RESERVE_CLASSES
            ),
        )
        return {"reserve_data": data, "reserve_domains": block}


class ReserveOfferComponent(ModelComponent):
    name = "reserve_offers"
    supported_formulations = _SUPPORTED
    requires = frozenset({"reserve_data", "reserve_domains", "generation", "purchase"})
    provides = frozenset(
        {
            "reserve",
            "reserve_block",
            "plsr_maximum",
            "reserve_interruptible_limit",
            "reserve_offer_definition",
            "energy_reserve_maximum",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        data = _data(context)
        domains = context.artifacts["reserve_domains"]
        generation = context.artifacts["generation"]
        purchase = context.artifacts["purchase"]
        block = pyo.Block(concrete=True)
        context.model.add_component("ReserveOffers", block)
        block.Reserve = pyo.Var(
            domains.ReserveOffer,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, offer, reserve_class, reserve_type: (
                0.0,
                None
                if any(
                    data.reserve_block_limit[
                        ca,
                        dt,
                        offer,
                        tranche,
                        reserve_class,
                        reserve_type,
                    ]
                    > 0.0
                    for tranche in BLOCKS
                )
                else 0.0,
            ),
        )
        block.ReserveBlock = pyo.Var(
            domains.ReserveBlock,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, offer, tranche, reserve_class, reserve_type: (
                0.0,
                data.reserve_block_limit[
                    ca, dt, offer, tranche, reserve_class, reserve_type
                ],
            ),
        )
        block.PLSRReserveProportionMaximum = pyo.Constraint(
            domains.ReserveBlock,
            rule=lambda _b, ca, dt, offer, tranche, reserve_class, reserve_type: (
                _b.ReserveBlock[ca, dt, offer, tranche, reserve_class, reserve_type]
                <= data.reserve_offer_percent.get(
                    (ca, dt, offer, tranche, reserve_class), 0.0
                )
                * generation[ca, dt, offer]
                if reserve_type == "PLRO"
                and data.reserve_block_limit[
                    ca, dt, offer, tranche, reserve_class, reserve_type
                ]
                > 0.0
                else pyo.Constraint.Skip
            ),
        )
        interruptible = [
            (*offer, reserve_class, "ILRO")
            for offer in case.offers
            for reserve_class in RESERVE_CLASSES
            if offer in case.bids
            and sum(case.bid_limit[key] for key in case.bid_blocks if key[:3] == offer)
            >= 0.0
        ]
        block.InterruptibleDomain = pyo.Set(
            dimen=5, ordered=True, initialize=sorted(interruptible)
        )
        block.ReserveInterruptibleOfferLimit = pyo.Constraint(
            block.InterruptibleDomain,
            rule=lambda _b, ca, dt, offer, reserve_class, reserve_type: (
                _b.Reserve[ca, dt, offer, reserve_class, reserve_type]
                <= purchase[ca, dt, offer]
            ),
        )
        block.ReserveOfferDefinition = pyo.Constraint(
            domains.ReserveOffer,
            rule=lambda _b, ca, dt, offer, reserve_class, reserve_type: (
                _b.Reserve[ca, dt, offer, reserve_class, reserve_type]
                == sum(
                    _b.ReserveBlock[
                        ca,
                        dt,
                        offer,
                        tranche,
                        reserve_class,
                        reserve_type,
                    ]
                    for tranche in BLOCKS
                )
            ),
        )
        block.EnergyAndReserveMaximum = pyo.Constraint(
            [
                (offer, reserve_class)
                for offer in case.offers
                for reserve_class in RESERVE_CLASSES
            ],
            rule=lambda _b, ca, dt, offer, reserve_class: (
                generation[ca, dt, offer]
                + data.reserve_maximum_factor.get((ca, dt, offer, reserve_class), 0.0)
                * sum(
                    _b.Reserve[ca, dt, offer, reserve_class, reserve_type]
                    for reserve_type in ("PLRO", "TWRO")
                )
                <= data.reserve_generation_maximum.get((ca, dt, offer), 0.0)
            ),
        )
        return {
            "reserve": block.Reserve,
            "reserve_block": block.ReserveBlock,
            "plsr_maximum": block.PLSRReserveProportionMaximum,
            "reserve_interruptible_limit": block.ReserveInterruptibleOfferLimit,
            "reserve_offer_definition": block.ReserveOfferDefinition,
            "energy_reserve_maximum": block.EnergyAndReserveMaximum,
        }


class ReserveScarcityComponent(ModelComponent):
    name = "reserve_scarcity"
    supported_formulations = _SUPPORTED
    requires = frozenset({"reserve_data", "reserve_domains"})
    provides = frozenset(
        {
            "reserve_shortfall",
            "reserve_shortfall_block",
            "reserve_shortfall_unit",
            "reserve_shortfall_unit_block",
            "reserve_shortfall_group",
            "reserve_shortfall_group_block",
            "reserve_shortfall_definitions",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["reserve_domains"]
        block = pyo.Block(concrete=True)
        context.model.add_component("ReserveScarcity", block)
        block.ReserveShortfall = pyo.Var(domains.Shortfall, domain=pyo.NonNegativeReals)
        shortfall_blocks = [
            (*island, reserve_class, risk, tranche)
            for island in domains.Island
            for reserve_class in RESERVE_CLASSES
            for risk in data.hvdc_risks | data.manual_risks | data.hvdc_secondary_risks
            for tranche in BLOCKS
            if (*island, reserve_class, risk) in domains.Shortfall
            or data.reserve_scarcity_price.get((*island, reserve_class, tranche), 0.0)
            != 0.0
        ]
        block.ReserveShortfallBlock = pyo.Var(
            shortfall_blocks,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, island, reserve_class, risk, tranche: (
                0.0,
                data.reserve_scarcity_limit.get(
                    (ca, dt, island, reserve_class, tranche), 0.0
                ),
            ),
        )
        block.ReserveShortfallUnit = pyo.Var(
            domains.ShortfallUnit, domain=pyo.NonNegativeReals
        )
        block.ReserveShortfallUnitBlock = pyo.Var(
            [
                (*generator, reserve_class, risk, tranche)
                for generator in data.risk_generators
                for reserve_class in RESERVE_CLASSES
                for risk in data.generator_risks | data.hvdc_secondary_risks
                for tranche in BLOCKS
                if (*generator, reserve_class, risk) in domains.ShortfallUnit
                or data.reserve_scarcity_price.get(
                    (generator[0], generator[1], generator[2], reserve_class, tranche),
                    0.0,
                )
                != 0.0
            ],
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, island, offer, reserve_class, risk, tranche: (
                0.0,
                data.reserve_scarcity_limit.get(
                    (ca, dt, island, reserve_class, tranche), 0.0
                ),
            ),
        )
        block.ReserveShortfallGroup = pyo.Var(
            domains.ShortfallGroup, domain=pyo.NonNegativeReals
        )
        group_names = sorted({key[3] for key in data.island_risk_group})
        block.ReserveShortfallGroupBlock = pyo.Var(
            [
                (*island, group, reserve_class, risk, tranche)
                for island in domains.Island
                for group in group_names
                for reserve_class in RESERVE_CLASSES
                for risk in data.group_risks
                for tranche in BLOCKS
                if (*island, group, reserve_class, risk) in domains.ShortfallGroup
                or data.reserve_scarcity_price.get(
                    (*island, reserve_class, tranche), 0.0
                )
                != 0.0
            ],
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, island, group, reserve_class, risk, tranche: (
                0.0,
                data.reserve_scarcity_limit.get(
                    (ca, dt, island, reserve_class, tranche), 0.0
                ),
            ),
        )
        block.ShortfallDefinitions = pyo.ConstraintList()
        for key in domains.Shortfall:
            block.ShortfallDefinitions.add(
                block.ReserveShortfall[key]
                == sum(block.ReserveShortfallBlock[*key, tranche] for tranche in BLOCKS)
            )
        for key in domains.ShortfallUnit:
            block.ShortfallDefinitions.add(
                block.ReserveShortfallUnit[key]
                == sum(
                    block.ReserveShortfallUnitBlock[*key, tranche] for tranche in BLOCKS
                )
            )
        for key in domains.ShortfallGroup:
            block.ShortfallDefinitions.add(
                block.ReserveShortfallGroup[key]
                == sum(
                    block.ReserveShortfallGroupBlock[*key, tranche]
                    for tranche in BLOCKS
                )
            )
        return {
            "reserve_shortfall": block.ReserveShortfall,
            "reserve_shortfall_block": block.ReserveShortfallBlock,
            "reserve_shortfall_unit": block.ReserveShortfallUnit,
            "reserve_shortfall_unit_block": block.ReserveShortfallUnitBlock,
            "reserve_shortfall_group": block.ReserveShortfallGroup,
            "reserve_shortfall_group_block": block.ReserveShortfallGroupBlock,
            "reserve_shortfall_definitions": block.ShortfallDefinitions,
        }


class ReserveRiskComponent(ModelComponent):
    name = "reserve_risk"
    supported_formulations = _SUPPORTED
    requirement_adjustments_in_risk = True
    requires = frozenset(
        {
            "reserve_data",
            "reserve_domains",
            "reserve",
            "reserve_shortfall",
            "reserve_shortfall_unit",
            "reserve_shortfall_group",
            "generation",
            "hvdc_flow",
            "hvdc_loss",
            "branch_flow",
            "reserve_share_effective",
            "hvdc_send_zero_binary",
        }
    )
    provides = frozenset(
        {
            "island_risk",
            "generator_island_risk",
            "group_island_risk",
            "hvdc_generator_island_risk",
            "hvdc_manual_island_risk",
            "hvdc_received",
            "risk_offset",
            "risk_constraints",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        data = _data(context)
        domains = context.artifacts["reserve_domains"]
        reserve = context.artifacts["reserve"]
        generation = context.artifacts["generation"]
        hvdc_flow = context.artifacts["hvdc_flow"]
        hvdc_loss = context.artifacts["hvdc_loss"]
        branch_flow = context.artifacts["branch_flow"]
        hvdc_send_zero = context.artifacts["hvdc_send_zero_binary"]
        shortfall = context.artifacts["reserve_shortfall"]
        shortfall_unit = context.artifacts["reserve_shortfall_unit"]
        shortfall_group = context.artifacts["reserve_shortfall_group"]
        assert case.hvdc is not None
        assert case.network is not None
        hvdc = case.hvdc
        network = case.network
        block = pyo.Block(concrete=True)
        context.model.add_component("ReserveRisk", block)
        block.IslandRisk = pyo.Var(domains.IslandRisk, domain=pyo.Reals)
        block.GeneratorIslandRisk = pyo.Var(domains.GeneratorRisk, domain=pyo.Reals)
        block.GroupIslandRisk = pyo.Var(domains.RiskGroup, domain=pyo.Reals)
        secondary_generator_domain = [
            (*generator, reserve_class, risk)
            for generator in data.risk_generators
            for reserve_class in RESERVE_CLASSES
            for risk in data.hvdc_secondary_risks
            if data.hvdc_secondary_enabled.get(
                (generator[0], generator[1], generator[2], risk), 0.0
            )
        ]
        secondary_manual_domain = [
            (*island, reserve_class, risk)
            for island in domains.Island
            for reserve_class in RESERVE_CLASSES
            for risk in data.hvdc_secondary_risks
            if data.hvdc_secondary_enabled.get((*island, risk), 0.0)
        ]
        block.HVDCGeneratorIslandRisk = pyo.Var(
            secondary_generator_domain, domain=pyo.Reals
        )
        block.HVDCManualIslandRisk = pyo.Var(secondary_manual_domain, domain=pyo.Reals)
        block.HVDCReceived = pyo.Var(domains.Island, domain=pyo.Reals)
        block.RiskOffset = pyo.Var(
            [key for key in domains.IslandRisk if key[4] in data.hvdc_risks],
            domain=pyo.Reals,
        )
        block.Constraints = pyo.ConstraintList()
        for island in domains.Island:
            ca, dt, island_name = island
            block.Constraints.add(
                block.HVDCReceived[island]
                == sum(
                    -hvdc_flow[link]
                    for link in hvdc.links
                    for *prefix, bus in hvdc.sending_bus
                    if tuple(prefix) == link
                    and (ca, dt, bus, island_name) in network.bus_island
                )
                + sum(
                    hvdc_flow[link] - hvdc_loss[link]
                    for link in hvdc.links
                    for *prefix, bus in hvdc.receiving_bus
                    if tuple(prefix) == link
                    and (ca, dt, bus, island_name) in network.bus_island
                )
            )
        effective = context.artifacts["reserve_share_effective"]
        for key in domains.IslandRisk:
            ca, dt, island, reserve_class, risk = key
            adjustment = data.risk_adjustment_factor.get(key, 0.0)
            shared = (
                _optional(effective, key)
                if self.requirement_adjustments_in_risk
                else 0.0
            )
            risk_shortfall = (
                _optional(shortfall, key)
                if self.requirement_adjustments_in_risk
                else 0.0
            )
            if risk in data.hvdc_risks:
                block.Constraints.add(
                    block.RiskOffset[key]
                    == data.free_reserve.get(key, 0.0)
                    + (
                        data.hvdc_pole_ramp_up.get(key, 0.0)
                        if risk in data.ce_risks
                        else 0.0
                    )
                )
                block.Constraints.add(
                    block.IslandRisk[key]
                    == adjustment
                    * (
                        block.HVDCReceived[ca, dt, island]
                        - block.RiskOffset[key]
                        + data.modulation_risk_class.get((ca, dt, risk), 0.0)
                    )
                    - risk_shortfall
                )
            elif risk in data.manual_risks:
                block.Constraints.add(
                    block.IslandRisk[key]
                    == adjustment
                    * (
                        data.risk_minimum.get(key, 0.0)
                        - data.free_reserve.get(key, 0.0)
                    )
                    - shared
                    - risk_shortfall
                )
        for key in domains.GeneratorRisk:
            ca, dt, island, offer, reserve_class, risk = key
            total_reserve = sum(
                reserve[ca, dt, offer, reserve_class, reserve_type]
                for reserve_type in RESERVE_TYPES
            )
            block.Constraints.add(
                block.GeneratorIslandRisk[key]
                == data.risk_adjustment_factor.get(
                    (ca, dt, island, reserve_class, risk), 0.0
                )
                * (
                    generation[ca, dt, offer]
                    - data.secondary_risk_offer.get((ca, dt, offer, risk), 0.0)
                    - data.free_reserve.get((ca, dt, island, reserve_class, risk), 0.0)
                    + data.fk_band.get((ca, dt, offer), 0.0)
                    + total_reserve
                    + sum(
                        generation[ca, dt, secondary]
                        + sum(
                            reserve[
                                ca,
                                dt,
                                secondary,
                                reserve_class,
                                reserve_type,
                            ]
                            for reserve_type in RESERVE_TYPES
                        )
                        for (
                            p_ca,
                            p_dt,
                            primary,
                            secondary,
                        ) in data.primary_secondary_offer
                        if (p_ca, p_dt, primary) == (ca, dt, offer)
                    )
                )
                - (
                    effective[ca, dt, island, reserve_class, risk]
                    if self.requirement_adjustments_in_risk
                    else 0.0
                )
                - (
                    _optional(shortfall_unit, key)
                    if self.requirement_adjustments_in_risk
                    else 0.0
                )
            )
            block.Constraints.add(
                block.IslandRisk[ca, dt, island, reserve_class, risk]
                >= block.GeneratorIslandRisk[key]
            )
        for key in domains.RiskGroup:
            ca, dt, island, group, reserve_class, risk = key
            group_offer = [
                offer
                for r_ca, r_dt, r_group, offer, r_risk in data.risk_group_offer
                if (r_ca, r_dt, r_group, r_risk) == (ca, dt, group, risk)
                and (ca, dt, offer) in case.offers
            ]
            directional = (ca, dt, island, group, risk) in data.island_link_risk_group
            gross = (
                sum(
                    branch_flow[ca, dt, branch] * factor
                    for (
                        f_ca,
                        f_dt,
                        f_group,
                        branch,
                        f_risk,
                    ), factor in data.directional_risk_factor.items()
                    if (f_ca, f_dt, f_group, f_risk) == (ca, dt, group, risk)
                )
                + sum(
                    reserve[ca, dt, offer, reserve_class, reserve_type]
                    for offer in group_offer
                    for reserve_type in RESERVE_TYPES
                )
                if directional
                else sum(
                    generation[ca, dt, offer]
                    + data.fk_band.get((ca, dt, offer), 0.0)
                    + sum(
                        reserve[ca, dt, offer, reserve_class, reserve_type]
                        for reserve_type in RESERVE_TYPES
                    )
                    for offer in group_offer
                )
            )
            block.Constraints.add(
                block.GroupIslandRisk[key]
                == data.risk_adjustment_factor.get(
                    (ca, dt, island, reserve_class, risk), 0.0
                )
                * (
                    gross
                    - data.secondary_risk_group.get((ca, dt, group, risk), 0.0)
                    - data.free_reserve.get((ca, dt, island, reserve_class, risk), 0.0)
                )
                - (
                    _optional(shortfall_group, key)
                    if self.requirement_adjustments_in_risk
                    else 0.0
                )
                - (
                    effective[ca, dt, island, reserve_class, risk]
                    if self.requirement_adjustments_in_risk
                    else 0.0
                )
            )
            block.Constraints.add(
                block.IslandRisk[ca, dt, island, reserve_class, risk]
                >= block.GroupIslandRisk[key]
            )
        for key in secondary_generator_domain:
            ca, dt, island, offer, reserve_class, risk = key
            gross = (
                generation[ca, dt, offer]
                + data.fk_band.get((ca, dt, offer), 0.0)
                + sum(
                    reserve[ca, dt, offer, reserve_class, reserve_type]
                    for reserve_type in RESERVE_TYPES
                )
                + sum(
                    generation[ca, dt, secondary]
                    + sum(
                        reserve[ca, dt, secondary, reserve_class, reserve_type]
                        for reserve_type in RESERVE_TYPES
                    )
                    for p_ca, p_dt, primary, secondary in data.primary_secondary_offer
                    if (p_ca, p_dt, primary) == (ca, dt, offer)
                )
                + block.HVDCReceived[ca, dt, island]
                - data.hvdc_secondary_subtractor.get((ca, dt, island), 0.0)
                - data.free_reserve.get((ca, dt, island, reserve_class, risk), 0.0)
                + data.modulation_risk_class.get((ca, dt, risk), 0.0)
            )
            block.Constraints.add(
                block.HVDCGeneratorIslandRisk[key]
                == data.risk_adjustment_factor.get(
                    (ca, dt, island, reserve_class, risk), 0.0
                )
                * gross
                - (
                    _optional(shortfall_unit, key)
                    if self.requirement_adjustments_in_risk
                    else 0.0
                )
                - data.big_m
                * hvdc_send_zero[ca, dt, island]
                * max(0, len(data.islands) - 1)
            )
            block.Constraints.add(
                block.IslandRisk[ca, dt, island, reserve_class, risk]
                >= block.HVDCGeneratorIslandRisk[key]
            )
        for key in secondary_manual_domain:
            ca, dt, island, reserve_class, risk = key
            block.Constraints.add(
                block.HVDCManualIslandRisk[key]
                == data.risk_adjustment_factor.get(key, 0.0)
                * (
                    data.risk_minimum.get(key, 0.0)
                    - data.free_reserve.get(key, 0.0)
                    + block.HVDCReceived[ca, dt, island]
                    - data.hvdc_secondary_subtractor.get((ca, dt, island), 0.0)
                    + data.modulation_risk_class.get((ca, dt, risk), 0.0)
                )
                - (
                    _optional(shortfall, key)
                    if self.requirement_adjustments_in_risk
                    else 0.0
                )
                - data.big_m
                * hvdc_send_zero[ca, dt, island]
                * max(0, len(data.islands) - 1)
            )
            block.Constraints.add(
                block.IslandRisk[key] >= block.HVDCManualIslandRisk[key]
            )
        return {
            "island_risk": block.IslandRisk,
            "generator_island_risk": block.GeneratorIslandRisk,
            "group_island_risk": block.GroupIslandRisk,
            "hvdc_generator_island_risk": block.HVDCGeneratorIslandRisk,
            "hvdc_manual_island_risk": block.HVDCManualIslandRisk,
            "hvdc_received": block.HVDCReceived,
            "risk_offset": block.RiskOffset,
            "risk_constraints": block.Constraints,
        }


class ReserveSharingComponent(ModelComponent):
    name = "reserve_sharing"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "reserve_data",
            "reserve_domains",
            "hvdc_data",
            "hvdc_flow",
            "island_reserve",
        }
    )
    provides = frozenset(
        {
            "shared_nfr",
            "shared_reserve",
            "hvdc_sent",
            "hvdc_sent_loss",
            "reserve_share_effective",
            "reserve_share_received",
            "reserve_share_sent",
            "reserve_share_penalty",
            "reserve_share_effective_ce",
            "reserve_share_effective_ece",
            "hvdc_sending_binary",
            "hvdc_send_zero_binary",
            "in_zone_binary",
            "lambda_hvdc_energy",
            "lambda_hvdc_reserve",
            "lambda_hvdc_energy_interval",
            "lambda_hvdc_reserve_interval",
            "sharing_constraints",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        data = _data(context)
        domains = context.artifacts["reserve_domains"]
        hvdc_flow = context.artifacts["hvdc_flow"]
        island_reserve = context.artifacts["island_reserve"]
        assert case.hvdc is not None
        assert case.network is not None
        hvdc = case.hvdc
        network = case.network
        block = pyo.Block(concrete=True)
        context.model.add_component("ReserveSharing", block)
        island_reserve_class = [
            (*island, rc) for island in domains.Island for rc in RESERVE_CLASSES
        ]
        directed = [
            (*key, direction)
            for key in island_reserve_class
            for direction in DIRECTIONS
        ]
        effective_domain = [
            (*key, risk)
            for key in island_reserve_class
            for risk in data.shareable_risks
        ]
        block.SharedNFR = pyo.Var(
            domains.Island,
            domain=pyo.NonNegativeReals,
            bounds=lambda _b, ca, dt, island: (
                0.0,
                max(0.0, data.shared_nfr_maximum[ca, dt, island]),
            ),
        )
        block.SharedReserve = pyo.Var(island_reserve_class, domain=pyo.NonNegativeReals)
        block.HVDCSent = pyo.Var(domains.Island, domain=pyo.NonNegativeReals)
        block.HVDCSentLoss = pyo.Var(domains.Island, domain=pyo.NonNegativeReals)
        block.ReserveShareEffective = pyo.Var(
            effective_domain, domain=pyo.NonNegativeReals
        )
        block.ReserveShareReceived = pyo.Var(directed, domain=pyo.NonNegativeReals)
        block.ReserveShareSent = pyo.Var(directed, domain=pyo.NonNegativeReals)
        block.ReserveSharePenalty = pyo.Var(
            sorted(case.periods), domain=pyo.NonNegativeReals
        )
        block.ReserveShareEffectiveCE = pyo.Var(
            island_reserve_class, domain=pyo.NonNegativeReals
        )
        block.ReserveShareEffectiveECE = pyo.Var(
            island_reserve_class, domain=pyo.NonNegativeReals
        )
        block.HVDCSending = pyo.Var(domains.Island, domain=pyo.Binary)
        block.HVDCSendZero = pyo.Var(domains.Island, domain=pyo.Binary)
        block.InZone = pyo.Var(
            [(*key, zone) for key in island_reserve_class for zone in ZONES],
            domain=pyo.Binary,
        )
        for key in block.InZone:
            round_power_key = (key[0], key[1], key[3])
            if key[-1] == "RP" and not data.reserve_round_power.get(
                round_power_key, 0.0
            ):
                block.InZone[key].fix(0.0)
            if (
                key[3] == "SIR"
                and key[-1] == "NR"
                and data.reserve_round_power.get(round_power_key, 0.0)
            ):
                block.InZone[key].fix(0.0)
        block.LambdaHVDCEnergy = pyo.Var(
            [(*island, bp) for island in domains.Island for bp in ENERGY_BREAKPOINTS],
            domain=pyo.NonNegativeReals,
        )
        block.LambdaHVDCReserve = pyo.Var(
            [(*key, bp) for key in directed for bp in RESERVE_BREAKPOINTS],
            domain=pyo.NonNegativeReals,
        )
        block.HVDCReserveSent = pyo.Var(directed, domain=pyo.Reals)
        block.HVDCReserveLoss = pyo.Var(directed, domain=pyo.Reals)
        block.Constraints = pyo.ConstraintList()
        for island in domains.Island:
            ca, dt, island_name = island
            block.Constraints.add(
                block.HVDCSent[island]
                == sum(
                    hvdc_flow[link]
                    for link in hvdc.links
                    for *prefix, bus in hvdc.sending_bus
                    if tuple(prefix) == link
                    and (ca, dt, bus, island_name) in network.bus_island
                )
            )
            block.Constraints.add(
                block.HVDCSent[island] <= data.big_m * block.HVDCSending[island]
            )
            block.Constraints.add(
                block.HVDCSent[island]
                <= data.big_m * (1.0 - block.HVDCSendZero[island])
            )
            block.Constraints.add(
                sum(block.LambdaHVDCEnergy[*island, bp] for bp in ENERGY_BREAKPOINTS)
                == 1.0
            )
            block.Constraints.add(
                block.HVDCSent[island]
                == sum(
                    data.energy_breakpoint_flow[*island, bp]
                    * block.LambdaHVDCEnergy[*island, bp]
                    for bp in ENERGY_BREAKPOINTS
                )
            )
            block.Constraints.add(
                block.HVDCSentLoss[island]
                == sum(
                    data.energy_breakpoint_loss[*island, bp]
                    * block.LambdaHVDCEnergy[*island, bp]
                    for bp in ENERGY_BREAKPOINTS
                )
            )
        for period in case.periods:
            block.Constraints.add(
                sum(
                    block.HVDCSending[island]
                    for island in domains.Island
                    if island[:2] == period
                )
                == 1.0
            )
            for reserve_class in RESERVE_CLASSES:
                block.Constraints.add(
                    sum(
                        block.InZone[*island, reserve_class, zone]
                        for island in domains.Island
                        if island[:2] == period
                        for zone in ZONES
                    )
                    == 1.0
                )
            block.Constraints.add(
                block.ReserveSharePenalty[period]
                == 1e-5
                * sum(
                    block.SharedNFR[island]
                    for island in domains.Island
                    if island[:2] == period
                )
                + 2e-5
                * sum(
                    block.SharedReserve[key]
                    for key in island_reserve_class
                    if key[:2] == period
                )
                + 3e-5
                * sum(
                    block.ReserveShareEffectiveCE[key]
                    + block.ReserveShareEffectiveECE[key]
                    for key in island_reserve_class
                    if key[:2] == period
                )
            )
        for key in island_reserve_class:
            ca, dt, island, reserve_class = key
            block.Constraints.add(
                block.HVDCSending[ca, dt, island]
                == sum(block.InZone[*key, zone] for zone in ZONES)
            )
            block.Constraints.add(block.SharedReserve[key] <= island_reserve[key])
            block.Constraints.add(
                block.HVDCSent[ca, dt, island]
                <= data.round_power_zone_exit[ca, dt, reserve_class]
                + data.big_m * (1.0 - block.InZone[*key, "RP"])
            )
            if data.reserve_share_enabled.get((ca, dt, reserve_class), 0.0):
                block.Constraints.add(
                    block.ReserveShareReceived[*key, "backward"]
                    + (
                        block.ReserveShareSent[*key, "forward"]
                        if not data.reserve_round_power.get(
                            (ca, dt, reserve_class), 0.0
                        )
                        else 0.0
                    )
                    <= data.big_m * (1.0 - block.InZone[*key, "NR"])
                )
            for risk in data.shareable_risks:
                effective_key = (*key, risk)
                block.Constraints.add(
                    block.ReserveShareEffective[effective_key]
                    <= sum(
                        block.ReserveShareReceived[*key, direction]
                        * data.effective_factor.get(effective_key, 0.0)
                        for direction in DIRECTIONS
                    )
                )
                target = (
                    block.ReserveShareEffectiveCE[key]
                    if risk in data.ce_risks
                    else block.ReserveShareEffectiveECE[key]
                )
                block.Constraints.add(
                    target >= block.ReserveShareEffective[effective_key]
                )
            for direction in DIRECTIONS:
                dkey = (*key, direction)
                block.Constraints.add(
                    block.ReserveShareSent[dkey]
                    <= block.SharedReserve[key]
                    + (
                        block.SharedNFR[ca, dt, island]
                        if reserve_class == "FIR"
                        else 0.0
                    )
                )
                block.Constraints.add(
                    block.ReserveShareSent[dkey]
                    <= max(
                        0.0,
                        data.hvdc_control_band[ca, dt, direction]
                        - data.modulation_risk[ca, dt],
                    )
                )
                if direction == "forward":
                    block.Constraints.add(
                        block.ReserveShareSent[dkey] + block.HVDCSent[ca, dt, island]
                        <= max(
                            0.0,
                            data.hvdc_maximum[ca, dt, island]
                            - data.modulation_risk[ca, dt],
                        )
                    )
                    block.Constraints.add(
                        block.ReserveShareReceived[dkey]
                        <= data.big_m * (1.0 - block.HVDCSending[ca, dt, island])
                    )
                    block.Constraints.add(
                        block.HVDCReserveSent[dkey]
                        == block.ReserveShareSent[dkey] + block.HVDCSent[ca, dt, island]
                    )
                else:
                    block.Constraints.add(
                        block.ReserveShareSent[dkey]
                        <= data.big_m * (1.0 - block.HVDCSending[ca, dt, island])
                    )
                    block.Constraints.add(
                        block.ReserveShareReceived[dkey]
                        <= block.HVDCSending[ca, dt, island]
                        * max(
                            0.0,
                            data.hvdc_control_band[ca, dt, direction]
                            - data.modulation_risk[ca, dt],
                        )
                    )
                    block.Constraints.add(
                        block.ReserveShareReceived[dkey]
                        <= block.HVDCSent[ca, dt, island]
                        - data.monopole_minimum[ca, dt]
                        - data.modulation_risk[ca, dt]
                        + data.big_m * (1.0 - block.InZone[*key, "RZ"])
                    )
                    block.Constraints.add(
                        block.HVDCReserveSent[dkey]
                        == block.HVDCSent[ca, dt, island]
                        - block.ReserveShareReceived[dkey]
                    )
                block.Constraints.add(
                    sum(
                        block.LambdaHVDCReserve[*dkey, bp] for bp in RESERVE_BREAKPOINTS
                    )
                    == 1.0
                )
                block.Constraints.add(
                    block.HVDCReserveSent[dkey]
                    == sum(
                        data.reserve_breakpoint_flow[*key[:3], bp]
                        * block.LambdaHVDCReserve[*dkey, bp]
                        for bp in RESERVE_BREAKPOINTS
                    )
                )
                block.Constraints.add(
                    block.HVDCReserveLoss[dkey]
                    == sum(
                        data.reserve_breakpoint_loss[*key[:3], bp]
                        * block.LambdaHVDCReserve[*dkey, bp]
                        for bp in RESERVE_BREAKPOINTS
                    )
                )
        # Cross-island received-flow identities.
        for dkey in directed:
            ca, dt, island, reserve_class, direction = dkey
            others = [
                other
                for other in domains.Island
                if other[:2] == (ca, dt) and other[2] != island
            ]
            if direction == "forward":
                block.Constraints.add(
                    block.ReserveShareReceived[dkey]
                    == sum(
                        block.ReserveShareSent[*other, reserve_class, direction]
                        - block.HVDCReserveLoss[*other, reserve_class, direction]
                        + block.HVDCSentLoss[other]
                        for other in others
                    )
                )
            else:
                block.Constraints.add(
                    block.ReserveShareReceived[dkey]
                    == sum(
                        block.ReserveShareSent[*other, reserve_class, direction]
                        for other in others
                    )
                    - block.HVDCReserveLoss[dkey]
                    + block.HVDCSentLoss[ca, dt, island]
                )
        energy_intervals = [
            (*island, left)
            for island in domains.Island
            for left in ENERGY_BREAKPOINTS[:-1]
        ]
        reserve_intervals = [
            (*key, left) for key in directed for left in RESERVE_BREAKPOINTS[:-1]
        ]
        portable_sos = data.enforce_nmir_sos2 and (
            hvdc.sos_representation is SosRepresentation.PORTABLE
        )
        native_sos = data.enforce_nmir_sos2 and (
            hvdc.sos_representation is SosRepresentation.NATIVE
        )
        block.LambdaHVDCEnergyInterval = pyo.Var(
            energy_intervals,
            domain=pyo.Binary if portable_sos else pyo.NonNegativeReals,
            bounds=(0.0, 1.0 if portable_sos else 0.0),
        )
        block.LambdaHVDCReserveInterval = pyo.Var(
            reserve_intervals,
            domain=pyo.Binary if portable_sos else pyo.NonNegativeReals,
            bounds=(0.0, 1.0 if portable_sos else 0.0),
        )
        block.PortableSOS2 = pyo.ConstraintList()
        if portable_sos:
            for island in domains.Island:
                block.PortableSOS2.add(
                    sum(
                        block.LambdaHVDCEnergyInterval[*island, left]
                        for left in ENERGY_BREAKPOINTS[:-1]
                    )
                    == 1.0
                )
                for position, breakpoint in enumerate(ENERGY_BREAKPOINTS):
                    adjacent = []
                    if position:
                        adjacent.append(
                            block.LambdaHVDCEnergyInterval[
                                *island, ENERGY_BREAKPOINTS[position - 1]
                            ]
                        )
                    if position < len(ENERGY_BREAKPOINTS) - 1:
                        adjacent.append(
                            block.LambdaHVDCEnergyInterval[*island, breakpoint]
                        )
                    block.PortableSOS2.add(
                        block.LambdaHVDCEnergy[*island, breakpoint] <= sum(adjacent)
                    )
            for key in directed:
                block.PortableSOS2.add(
                    sum(
                        block.LambdaHVDCReserveInterval[*key, left]
                        for left in RESERVE_BREAKPOINTS[:-1]
                    )
                    == 1.0
                )
                for position, breakpoint in enumerate(RESERVE_BREAKPOINTS):
                    adjacent = []
                    if position:
                        adjacent.append(
                            block.LambdaHVDCReserveInterval[
                                *key, RESERVE_BREAKPOINTS[position - 1]
                            ]
                        )
                    if position < len(RESERVE_BREAKPOINTS) - 1:
                        adjacent.append(
                            block.LambdaHVDCReserveInterval[*key, breakpoint]
                        )
                    block.PortableSOS2.add(
                        block.LambdaHVDCReserve[*key, breakpoint] <= sum(adjacent)
                    )
        elif native_sos:

            def energy_sos_rule(
                _b: pyo.Block, ca: str, dt: str, island: str
            ) -> Any:
                return (
                    [
                        block.LambdaHVDCEnergy[ca, dt, island, breakpoint]
                        for breakpoint in ENERGY_BREAKPOINTS
                    ],
                    list(range(1, len(ENERGY_BREAKPOINTS) + 1)),
                )

            block.NativeEnergySOS2 = pyo.SOSConstraint(
                domains.Island, rule=energy_sos_rule, sos=2
            )
            block.NativeReserveIndex = pyo.Set(
                dimen=5, ordered=True, initialize=directed
            )

            def reserve_sos_rule(
                _b: pyo.Block,
                ca: str,
                dt: str,
                island: str,
                reserve_class: str,
                direction: str,
            ) -> Any:
                return (
                    [
                        block.LambdaHVDCReserve[
                            ca,
                            dt,
                            island,
                            reserve_class,
                            direction,
                            breakpoint,
                        ]
                        for breakpoint in RESERVE_BREAKPOINTS
                    ],
                    list(range(1, len(RESERVE_BREAKPOINTS) + 1)),
                )

            block.NativeReserveSOS2 = pyo.SOSConstraint(
                block.NativeReserveIndex, rule=reserve_sos_rule, sos=2
            )
            for variable in block.LambdaHVDCEnergyInterval.values():
                variable.fix(0.0)
            for variable in block.LambdaHVDCReserveInterval.values():
                variable.fix(0.0)
        return {
            "shared_nfr": block.SharedNFR,
            "shared_reserve": block.SharedReserve,
            "hvdc_sent": block.HVDCSent,
            "hvdc_sent_loss": block.HVDCSentLoss,
            "reserve_share_effective": block.ReserveShareEffective,
            "reserve_share_received": block.ReserveShareReceived,
            "reserve_share_sent": block.ReserveShareSent,
            "reserve_share_penalty": block.ReserveSharePenalty,
            "reserve_share_effective_ce": block.ReserveShareEffectiveCE,
            "reserve_share_effective_ece": block.ReserveShareEffectiveECE,
            "hvdc_sending_binary": block.HVDCSending,
            "hvdc_send_zero_binary": block.HVDCSendZero,
            "in_zone_binary": block.InZone,
            "lambda_hvdc_energy": block.LambdaHVDCEnergy,
            "lambda_hvdc_reserve": block.LambdaHVDCReserve,
            "lambda_hvdc_energy_interval": block.LambdaHVDCEnergyInterval,
            "lambda_hvdc_reserve_interval": block.LambdaHVDCReserveInterval,
            "sharing_constraints": block.Constraints,
        }


class IslandReserveComponent(ModelComponent):
    name = "island_reserve"
    supported_formulations = _SUPPORTED
    requires = frozenset({"reserve_data", "reserve_domains", "reserve"})
    provides = frozenset({"island_reserve", "island_reserve_definition"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["reserve_domains"]
        reserve = context.artifacts["reserve"]
        block = pyo.Block(concrete=True)
        context.model.add_component("IslandReserve", block)
        island_class = [
            (*island, rc) for island in domains.Island for rc in RESERVE_CLASSES
        ]
        block.IslandReserve = pyo.Var(island_class, domain=pyo.NonNegativeReals)
        block.IslandReserveCalculation = pyo.Constraint(
            island_class,
            rule=lambda _b, ca, dt, island, reserve_class: (
                _b.IslandReserve[ca, dt, island, reserve_class]
                <= sum(
                    reserve[ca, dt, offer, reserve_class, reserve_type]
                    for o_ca, o_dt, offer, o_island in data.offer_island
                    if (o_ca, o_dt, o_island) == (ca, dt, island)
                    for reserve_type in RESERVE_TYPES
                )
            ),
        )
        return {
            "island_reserve": block.IslandReserve,
            "island_reserve_definition": block.IslandReserveCalculation,
        }


class ReserveRequirementComponent(ModelComponent):
    name = "reserve_requirement"
    supported_formulations = _SUPPORTED
    requires = frozenset({"reserve_domains", "island_risk", "island_reserve"})
    provides = frozenset(
        {"reserve_deficit_ce", "reserve_deficit_ece", "reserve_requirement"}
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["reserve_domains"]
        risk = context.artifacts["island_risk"]
        island_reserve = context.artifacts["island_reserve"]
        block = pyo.Block(concrete=True)
        context.model.add_component("ReserveRequirement", block)
        island_class = [
            (*island, reserve_class)
            for island in domains.Island
            for reserve_class in RESERVE_CLASSES
        ]
        block.DeficitReserveCE = pyo.Var(island_class, domain=pyo.NonNegativeReals)
        block.DeficitReserveECE = pyo.Var(island_class, domain=pyo.NonNegativeReals)
        block.SupplyDemandReserveRequirement = pyo.Constraint(
            domains.IslandRisk,
            rule=lambda _b, ca, dt, island, reserve_class, risk_class: (
                risk[ca, dt, island, reserve_class, risk_class]
                - (
                    _b.DeficitReserveCE[ca, dt, island, reserve_class]
                    if risk_class in data.ce_risks
                    else _b.DeficitReserveECE[ca, dt, island, reserve_class]
                )
                <= island_reserve[ca, dt, island, reserve_class]
            ),
        )
        return {
            "reserve_deficit_ce": block.DeficitReserveCE,
            "reserve_deficit_ece": block.DeficitReserveECE,
            "reserve_requirement": block.SupplyDemandReserveRequirement,
        }


class ReserveSecurityComponent(HVDCSecurityComponent):
    name = "network_security"
    supported_formulations = _SUPPORTED
    requires = HVDCSecurityComponent.requires | frozenset({"reserve_data", "reserve"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        artifacts = dict(super().build(context))
        data = _data(context)
        reserve = context.artifacts["reserve"]
        block = context.model.NetworkSecurity
        # Add reserve coefficients to the already-built market-node rows.
        for name in (
            "MNodeSecurityConstraintLE",
            "MNodeSecurityConstraintGE",
            "MNodeSecurityConstraintEQ",
        ):
            component = getattr(block, name)
            for key in list(component):
                constraint = component[key]
                extra = sum(
                    factor * reserve[ca, dt, offer, reserve_class, reserve_type]
                    for (
                        ca,
                        dt,
                        constraint_name,
                        offer,
                        reserve_class,
                        reserve_type,
                    ), factor in data.market_reserve_offer_factor.items()
                    if (ca, dt, constraint_name) == tuple(key)
                )
                if extra.__class__ is not int:
                    constraint.set_value(
                        (constraint.lower, constraint.body + extra, constraint.upper)
                    )
        return artifacts


class ReserveEconomicsComponent(HVDCEconomicsComponent):
    name = "network_economics"
    supported_formulations = _SUPPORTED
    requires = HVDCEconomicsComponent.requires | frozenset(
        {
            "reserve_data",
            "reserve_domains",
            "reserve_block",
            "reserve_shortfall_block",
            "reserve_shortfall_unit_block",
            "reserve_shortfall_group_block",
            "reserve_deficit_ce",
            "reserve_deficit_ece",
            "reserve_share_penalty",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        artifacts = dict(super().build(context))
        case = _case(context)
        data = _data(context)
        reserve_block = context.artifacts["reserve_block"]
        shortfall_block = context.artifacts["reserve_shortfall_block"]
        shortfall_unit_block = context.artifacts["reserve_shortfall_unit_block"]
        shortfall_group_block = context.artifacts["reserve_shortfall_group_block"]
        deficit_ce = context.artifacts["reserve_deficit_ce"]
        deficit_ece = context.artifacts["reserve_deficit_ece"]
        share_penalty = context.artifacts["reserve_share_penalty"]
        block = context.model.Economics
        block.del_component(block.SystemCostDefinition)
        block.SystemCostDefinition = pyo.Constraint(
            sorted(case.periods),
            rule=lambda _b, ca, dt: (
                _b.SystemCostByPeriod[ca, dt]
                == sum(
                    context.artifacts["generation_block"][key] * case.offer_price[key]
                    for key in case.offer_blocks
                    if key[:2] == (ca, dt)
                )
                + sum(
                    reserve_block[key] * data.reserve_block_price[key]
                    for key in reserve_block
                    if key[:2] == (ca, dt)
                )
            ),
        )
        original_penalty = block.SystemPenaltyDefinition
        original_penalty.deactivate()
        block.ReserveSystemPenaltyDefinition = pyo.Constraint(
            sorted(case.periods),
            rule=lambda _b, ca, dt: (
                _b.SystemPenaltyByPeriod[ca, dt]
                == _b.SystemPenaltyByPeriod[ca, dt]
                - original_penalty[ca, dt].body
                + sum(
                    data.deficit_reserve_ce_penalty * deficit_ce[key]
                    + data.deficit_reserve_ece_penalty * deficit_ece[key]
                    for key in deficit_ce
                    if key[:2] == (ca, dt)
                )
            ),
        )
        block.del_component(block.TotalScarcityCostDefinition)
        block.TotalScarcityCostDefinition = pyo.Constraint(
            sorted(case.periods),
            rule=lambda _b, ca, dt: (
                _b.ScarcityCostByPeriod[ca, dt]
                == sum(
                    context.artifacts["energy_scarcity_block"][key]
                    * case.scarcity_price[key]
                    for key in case.scarcity_blocks
                    if key[:2] == (ca, dt)
                )
                + sum(
                    data.reserve_scarcity_price.get(
                        (key[0], key[1], key[2], key[-3], key[-1]), 0.0
                    )
                    * shortfall_block[key]
                    for key in shortfall_block
                    if key[:2] == (ca, dt)
                )
                + sum(
                    data.reserve_scarcity_price.get(
                        (key[0], key[1], key[2], key[-3], key[-1]), 0.0
                    )
                    * shortfall_unit_block[key]
                    for key in shortfall_unit_block
                    if key[:2] == (ca, dt)
                )
                + sum(
                    data.reserve_scarcity_price.get(
                        (key[0], key[1], key[2], key[-3], key[-1]), 0.0
                    )
                    * shortfall_group_block[key]
                    for key in shortfall_group_block
                    if key[:2] == (ca, dt)
                )
            ),
        )
        block.del_component(block.Objective)
        block.del_component(block.NetBenefit)
        block.NetBenefit = pyo.Expression(
            expr=block.SystemBenefit
            - block.SystemCost
            - block.SystemPenalty
            - block.ScarcityCost
            - sum(share_penalty[key] for key in case.periods)
            + sum(
                case.scarcity_limit[key] * case.scarcity_price[key]
                for key in case.scarcity_blocks
            )
        )
        block.Objective = pyo.Objective(expr=block.NetBenefit, sense=pyo.maximize)
        artifacts.update(
            {
                "system_cost_definition": block.SystemCostDefinition,
                "system_penalty_definition": block.ReserveSystemPenaltyDefinition,
                "total_scarcity_definition": block.TotalScarcityCostDefinition,
                "net_benefit": block.NetBenefit,
                "objective": block.Objective,
            }
        )
        return artifacts


def _optional(component: Any, key: Key) -> Any:
    try:
        return component[key]
    except KeyError:
        return 0.0
