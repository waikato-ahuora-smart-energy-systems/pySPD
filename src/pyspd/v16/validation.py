"""Independent checks for the SPD v16 delta equations and price fallback."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.hvdc import HvdcSolveOutcome, audit_pricing_model
from pyspd.v16.data import Spd16Case

type Key = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Spd16ValidationReport:
    residuals: Mapping[str, float]
    tolerance: float
    pricing_model_audit_passed: bool
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "residuals", MappingProxyType(dict(self.residuals)))


class IndependentSpd16Validator:
    """Recompute v16-only relationships without reading constraint bodies."""

    def validate(
        self,
        outcome: HvdcSolveOutcome,
        reserve_prices: Mapping[Key, float],
        *,
        tolerance: float = 1e-6,
    ) -> Spd16ValidationReport:
        primary = outcome.primary_model
        case = primary.case_data
        if not isinstance(case, Spd16Case) or case.reserve is None:
            raise TypeError("SPD v16 validation requires Spd16Case")
        data = case.reserve
        artifacts = primary.artifacts
        residuals: dict[str, float] = {}

        generation_block = artifacts["generation_block"]
        positive = artifacts["tie_break_slack_positive"]
        negative = artifacts["tie_break_slack_negative"]
        for pair in case.tie_break_pairs:
            left = pair[:4]
            right = pair[:2] + pair[4:]
            expected = (
                _value(generation_block[left]) / case.capped_offer_block_mw[left]
                - _value(generation_block[right]) / case.capped_offer_block_mw[right]
            )
            residuals[f"tie_break:{pair}"] = abs(
                expected - _value(positive[pair]) + _value(negative[pair])
            )

        generation = artifacts["generation"]
        purchase = artifacts["purchase"]
        reserve = artifacts["reserve"]
        charging_mode = artifacts["battery_charging_mode"]
        assert case.network is not None
        for pair in case.battery_pairs:
            ca, dt, load_node, generation_node = pair
            charging = sum(
                _value(purchase[ca, dt, bid])
                for b_ca, b_dt, bid, node in case.network.bid_node
                if (b_ca, b_dt, node) == (ca, dt, load_node)
            ) + sum(
                _value(reserve[ca, dt, offer, reserve_class, "ILRO"])
                for o_ca, o_dt, offer, node in case.network.offer_node
                if (o_ca, o_dt, node) == (ca, dt, load_node)
                for reserve_class in ("FIR", "SIR")
            )
            discharging = sum(
                _value(generation[ca, dt, offer])
                for o_ca, o_dt, offer, node in case.network.offer_node
                if (o_ca, o_dt, node) == (ca, dt, generation_node)
            )
            mode = _value(charging_mode[pair])
            residuals[f"battery_charge:{pair}"] = max(0.0, charging - data.big_m * mode)
            residuals[f"battery_discharge:{pair}"] = max(
                0.0, discharging - data.big_m * (1.0 - mode)
            )
            residuals[f"battery_integrality:{pair}"] = min(abs(mode), abs(mode - 1.0))

        risk = artifacts["island_risk"]
        island_reserve = artifacts["island_reserve"]
        effective = artifacts["reserve_share_effective"]
        shortfall = artifacts["reserve_shortfall"]
        shortfall_unit = artifacts["reserve_shortfall_unit"]
        shortfall_group = artifacts["reserve_shortfall_group"]
        deficit_ece = artifacts["reserve_deficit_ece"]
        for key in risk:
            risk_key = tuple(key)
            covered = _value(risk[key])
            risk_class = risk_key[-1]
            if risk_class in data.shareable_risks:
                covered -= _optional_value(effective, risk_key)
            if risk_class in data.ce_risks:
                if risk_class not in data.generator_risks | data.link_risks:
                    covered -= _optional_value(shortfall, risk_key)
                if risk_class in data.generator_risks:
                    covered -= sum(
                        _value(shortfall_unit[item])
                        for item in shortfall_unit
                        if tuple(item)[:3] == risk_key[:3]
                        and tuple(item)[4:] == risk_key[3:]
                    )
                if risk_class in data.generator_risks | data.link_risks:
                    covered -= sum(
                        _value(shortfall_group[item])
                        for item in shortfall_group
                        if tuple(item)[:3] == risk_key[:3]
                        and tuple(item)[4:] == risk_key[3:]
                    )
            else:
                covered -= _value(deficit_ece[risk_key[:4]])
            residuals[f"reserve_requirement:{risk_key}"] = max(
                0.0, covered - _value(island_reserve[risk_key[:4]])
            )

        pricing = outcome.pricing_model
        definitions = pricing.artifacts["island_reserve_definition"]
        requirements = pricing.artifacts["reserve_requirement"]
        pricing_reserve = pricing.artifacts["island_reserve"]
        for key, published in reserve_prices.items():
            definition_dual = float(pricing.model.dual[definitions[key]])
            expected = definition_dual
            if abs(_value(pricing_reserve[key])) <= 1e-9:
                expected = sum(
                    float(pricing.model.dual[requirements[item]])
                    for item in requirements
                    if tuple(item)[:4] == key
                )
            residuals[f"reserve_price:{key}"] = abs(float(published) - expected)

        primary_objective = outcome.primary_snapshot.objective
        pricing_objective = outcome.pricing_snapshot.objective
        objective_residual = abs(primary_objective - pricing_objective)
        objective_scale = max(1.0, abs(primary_objective), abs(pricing_objective))
        residuals["fixed_rmip_objective"] = objective_residual
        residuals["fixed_rmip_objective_relative"] = (
            objective_residual / objective_scale
        )
        audit = audit_pricing_model(outcome)
        objective_passed = math.isclose(
            primary_objective,
            pricing_objective,
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
        passed = (
            audit.passed
            and objective_passed
            and all(
                math.isfinite(value) and value <= tolerance
                for name, value in residuals.items()
                if name != "fixed_rmip_objective"
            )
        )
        return Spd16ValidationReport(residuals, tolerance, audit.passed, passed)


def _value(value: Any) -> float:
    return float(pyo.value(value, exception=True))


def _optional_value(component: Any, key: Key) -> float:
    try:
        return _value(component[key])
    except KeyError:
        return 0.0
