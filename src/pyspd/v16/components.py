"""Replacement and additive Pyomo components for SPD Formulation v16."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuildContext, ModelComponent
from pyspd.reserve.components import ReserveEconomicsComponent, ReserveRiskComponent
from pyspd.reserve.data import RESERVE_CLASSES
from pyspd.v16.compatibility import SPD16_FORMULATION_ID
from pyspd.v16.data import Spd16Case

type Key = tuple[str, ...]

_SUPPORTED = frozenset({SPD16_FORMULATION_ID})


def _case(context: BuildContext) -> Spd16Case:
    if not isinstance(context.case_data, Spd16Case):
        raise TypeError("SPD v16 components require Spd16Case")
    return context.case_data


def _optional(component: Any, key: Key) -> Any:
    try:
        return component[key]
    except KeyError:
        return 0.0


class Spd16TieBreakComponent(ModelComponent):
    name = "spd16_tie_break"
    supported_formulations = _SUPPORTED
    requires = frozenset({"generation_block"})
    provides = frozenset(
        {"tie_break_slack_positive", "tie_break_slack_negative", "tie_break"}
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        generation_block = context.artifacts["generation_block"]
        block = pyo.Block(concrete=True)
        context.model.add_component("Spd16TieBreak", block)
        pairs = sorted(case.tie_break_pairs)
        block.Pair = pyo.Set(dimen=6, ordered=True, initialize=pairs)
        block.SlackPositive = pyo.Var(block.Pair, domain=pyo.NonNegativeReals)
        block.SlackNegative = pyo.Var(block.Pair, domain=pyo.NonNegativeReals)
        block.ProportionalDispatch = pyo.Constraint(
            block.Pair,
            rule=lambda _b, ca, dt, left, left_block, right, right_block: (
                generation_block[ca, dt, left, left_block]
                / case.capped_offer_block_mw[ca, dt, left, left_block]
                - generation_block[ca, dt, right, right_block]
                / case.capped_offer_block_mw[ca, dt, right, right_block]
                == _b.SlackPositive[ca, dt, left, left_block, right, right_block]
                - _b.SlackNegative[ca, dt, left, left_block, right, right_block]
            ),
        )
        return {
            "tie_break_slack_positive": block.SlackPositive,
            "tie_break_slack_negative": block.SlackNegative,
            "tie_break": block.ProportionalDispatch,
        }


class Spd16BatteryModeComponent(ModelComponent):
    name = "spd16_battery_mode"
    supported_formulations = _SUPPORTED
    requires = frozenset({"generation", "purchase", "reserve"})
    provides = frozenset(
        {"battery_charging_mode", "battery_charging_limit", "battery_discharging_limit"}
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        assert case.network is not None
        assert case.reserve is not None
        generation = context.artifacts["generation"]
        purchase = context.artifacts["purchase"]
        reserve = context.artifacts["reserve"]
        block = pyo.Block(concrete=True)
        context.model.add_component("Spd16BatteryMode", block)
        pairs = sorted(case.battery_pairs)
        block.Pair = pyo.Set(dimen=4, ordered=True, initialize=pairs)
        block.ChargingMode = pyo.Var(block.Pair, domain=pyo.Binary)
        block.ChargingLimit = pyo.Constraint(
            block.Pair,
            rule=lambda _b, ca, dt, load_node, generation_node: (
                sum(
                    purchase[ca, dt, bid]
                    for b_ca, b_dt, bid, node in case.network.bid_node
                    if (b_ca, b_dt, node) == (ca, dt, load_node)
                )
                + sum(
                    reserve[ca, dt, offer, reserve_class, "ILRO"]
                    for o_ca, o_dt, offer, node in case.network.offer_node
                    if (o_ca, o_dt, node) == (ca, dt, load_node)
                    for reserve_class in RESERVE_CLASSES
                )
                <= case.reserve.big_m
                * _b.ChargingMode[ca, dt, load_node, generation_node]
            ),
        )
        block.DischargingLimit = pyo.Constraint(
            block.Pair,
            rule=lambda _b, ca, dt, load_node, generation_node: (
                sum(
                    generation[ca, dt, offer]
                    for o_ca, o_dt, offer, node in case.network.offer_node
                    if (o_ca, o_dt, node) == (ca, dt, generation_node)
                )
                <= case.reserve.big_m
                * (1.0 - _b.ChargingMode[ca, dt, load_node, generation_node])
            ),
        )
        return {
            "battery_charging_mode": block.ChargingMode,
            "battery_charging_limit": block.ChargingLimit,
            "battery_discharging_limit": block.DischargingLimit,
        }


class Spd16ReserveRiskComponent(ReserveRiskComponent):
    """Keep gross risk calculation separate from v16 cover adjustments."""

    supported_formulations = _SUPPORTED
    requirement_adjustments_in_risk = False


class Spd16ReserveRequirementComponent(ModelComponent):
    name = "reserve_requirement"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "reserve_data",
            "reserve_domains",
            "island_risk",
            "island_reserve",
            "reserve_share_effective",
            "reserve_shortfall",
            "reserve_shortfall_unit",
            "reserve_shortfall_group",
        }
    )
    provides = frozenset(
        {"reserve_deficit_ce", "reserve_deficit_ece", "reserve_requirement"}
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        case = _case(context)
        assert case.reserve is not None
        data = case.reserve
        domains = context.artifacts["reserve_domains"]
        risk = context.artifacts["island_risk"]
        island_reserve = context.artifacts["island_reserve"]
        effective = context.artifacts["reserve_share_effective"]
        shortfall = context.artifacts["reserve_shortfall"]
        shortfall_unit = context.artifacts["reserve_shortfall_unit"]
        shortfall_group = context.artifacts["reserve_shortfall_group"]
        block = pyo.Block(concrete=True)
        context.model.add_component("ReserveRequirement", block)
        island_class = [
            (*island, reserve_class)
            for island in domains.Island
            for reserve_class in RESERVE_CLASSES
        ]
        block.DeficitReserveCE = pyo.Var(island_class, domain=pyo.NonNegativeReals)
        block.DeficitReserveECE = pyo.Var(island_class, domain=pyo.NonNegativeReals)

        def requirement(
            _b: pyo.Block,
            ca: str,
            dt: str,
            island: str,
            reserve_class: str,
            risk_class: str,
        ) -> Any:
            key = (ca, dt, island, reserve_class, risk_class)
            covered = risk[key]
            if risk_class in data.shareable_risks:
                covered -= _optional(effective, key)
            if risk_class in data.ce_risks:
                if risk_class not in data.generator_risks | data.link_risks:
                    covered -= _optional(shortfall, key)
                if risk_class in data.generator_risks:
                    covered -= sum(
                        shortfall_unit[item]
                        for item in shortfall_unit
                        if item[:3] == key[:3] and item[4:] == key[3:]
                    )
                if risk_class in data.generator_risks | data.link_risks:
                    covered -= sum(
                        shortfall_group[item]
                        for item in shortfall_group
                        if item[:3] == key[:3] and item[4:] == key[3:]
                    )
            else:
                covered -= _b.DeficitReserveECE[ca, dt, island, reserve_class]
            return covered <= island_reserve[ca, dt, island, reserve_class]

        block.SupplyDemandReserveRequirement = pyo.Constraint(
            domains.IslandRisk, rule=requirement
        )
        return {
            "reserve_deficit_ce": block.DeficitReserveCE,
            "reserve_deficit_ece": block.DeficitReserveECE,
            "reserve_requirement": block.SupplyDemandReserveRequirement,
        }


class Spd16ReserveEconomicsComponent(ReserveEconomicsComponent):
    """Use the v16 ECE-only deficit penalty and explicit tie-slack cost."""

    supported_formulations = _SUPPORTED
    requires = ReserveEconomicsComponent.requires | frozenset(
        {"tie_break_slack_positive", "tie_break_slack_negative"}
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        artifacts = dict(super().build(context))
        case = _case(context)
        assert case.reserve is not None
        deficit_ece = context.artifacts["reserve_deficit_ece"]
        positive = context.artifacts["tie_break_slack_positive"]
        negative = context.artifacts["tie_break_slack_negative"]
        block = context.model.Economics
        block.del_component(block.ReserveSystemPenaltyDefinition)
        original = block.SystemPenaltyDefinition
        block.Spd16SystemPenaltyDefinition = pyo.Constraint(
            sorted(case.periods),
            rule=lambda _b, ca, dt: (
                _b.SystemPenaltyByPeriod[ca, dt]
                == _b.SystemPenaltyByPeriod[ca, dt]
                - original[ca, dt].body
                + sum(
                    case.reserve.deficit_reserve_ece_penalty * deficit_ece[key]
                    for key in deficit_ece
                    if key[:2] == (ca, dt)
                )
                + case.tie_break_slack_price
                * sum(
                    positive[key] + negative[key]
                    for key in positive
                    if key[:2] == (ca, dt)
                )
            ),
        )
        artifacts["system_penalty_definition"] = block.Spd16SystemPenaltyDefinition
        return artifacts
