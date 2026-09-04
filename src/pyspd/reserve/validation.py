"""Independent Gate 7 reserve, risk, sharing, and scarcity validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.hvdc import HvdcSolveOutcome, IndependentHvdcValidator
from pyspd.reserve.data import (
    BLOCKS,
    CE_RISKS,
    DIRECTIONS,
    ENERGY_BREAKPOINTS,
    HVDC_RISKS,
    MANUAL_RISKS,
    RESERVE_BREAKPOINTS,
    RESERVE_CLASSES,
    RESERVE_TYPES,
    ReserveCase,
)
from pyspd.solver import HighsBackend, SolverConfiguration


@dataclass(frozen=True, slots=True)
class ReserveValidationReport:
    """Named residual evidence recomputed without reading model row bodies."""

    residuals: dict[str, float]
    tolerance: float
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "residuals", MappingProxyType(dict(self.residuals)))


@dataclass(frozen=True, slots=True)
class ReservePriceCheck:
    key: tuple[str, ...]
    perturbation_mw: float
    dual_price: float
    finite_difference_price: float
    absolute_error: float
    tolerance: float
    passed: bool


class IndependentReserveValidator:
    """Recompute physical and economic Gate 7 identities from solved primals."""

    def validate(
        self,
        outcome: HvdcSolveOutcome,
        *,
        tolerance: float = 1e-6,
    ) -> ReserveValidationReport:
        built = outcome.primary_model
        case = built.case_data
        if not isinstance(case, ReserveCase) or case.reserve is None:
            raise TypeError("reserve validation requires ReserveCase")
        data = case.reserve
        artifacts = built.artifacts
        reserve = artifacts["reserve"]
        reserve_block = artifacts["reserve_block"]
        generation = artifacts["generation"]
        island_reserve = artifacts["island_reserve"]
        island_risk = artifacts["island_risk"]
        deficit_ce = artifacts["reserve_deficit_ce"]
        deficit_ece = artifacts["reserve_deficit_ece"]
        residuals = dict(
            IndependentHvdcValidator()
            .validate(outcome, tolerance=tolerance)
            .residuals
        )

        for key in reserve:
            residuals[f"reserve_offer:{key}"] = abs(
                _value(reserve[key])
                - sum(
                    _value(reserve_block[*key[:3], block, *key[3:]])
                    for block in BLOCKS
                )
            )
        for offer in case.offers:
            for reserve_class in RESERVE_CLASSES:
                lhs = _value(generation[offer]) + data.reserve_maximum_factor.get(
                    (*offer, reserve_class), 0.0
                ) * sum(
                    _value(reserve[*offer, reserve_class, reserve_type])
                    for reserve_type in ("PLRO", "TWRO")
                )
                residuals[f"energy_reserve_maximum:{offer}:{reserve_class}"] = max(
                    0.0,
                    lhs - data.reserve_generation_maximum.get(offer, 0.0),
                )
        for island in data.islands:
            for reserve_class in RESERVE_CLASSES:
                key = (*island, reserve_class)
                available = sum(
                    _value(reserve[island[0], island[1], offer, reserve_class, reserve_type])
                    for ca, dt, offer, offer_island in data.offer_island
                    if (ca, dt, offer_island) == island
                    for reserve_type in RESERVE_TYPES
                )
                residuals[f"island_reserve:{key}"] = max(
                    0.0, _value(island_reserve[key]) - available
                )
        for key in island_risk:
            requirement = _value(island_risk[key]) - (
                _value(deficit_ce[key[:4]])
                if key[-1] in {"genRisk", "DCCE", "manual", "HVDCsecRisk"}
                else _value(deficit_ece[key[:4]])
            )
            residuals[f"risk_cover:{key}"] = max(
                0.0, requirement - _value(island_reserve[key[:4]])
            )

        self._shortfall_residuals(artifacts, residuals)
        self._risk_residuals(case, artifacts, residuals)
        self._sharing_residuals(case, artifacts, residuals, tolerance)
        self._canonicalization_residuals(outcome, residuals)
        self._objective_residuals(case, artifacts, residuals)
        passed = all(
            math.isfinite(value) and value <= tolerance
            for value in residuals.values()
        )
        return ReserveValidationReport(residuals, tolerance, passed)

    @staticmethod
    def _canonicalization_residuals(
        outcome: HvdcSolveOutcome,
        residuals: dict[str, float],
    ) -> None:
        audit = outcome.pricing_canonicalization
        if audit is None:
            return
        reserve_sent = outcome.pricing_model.artifacts["hvdc_reserve_sent"]
        for name, target in audit.accepted_targets.items():
            key = tuple(name.split("|"))
            residuals[f"pricing_canonicalization_target:{key}"] = abs(
                _value(reserve_sent[key]) - target
            )

    @staticmethod
    def _shortfall_residuals(
        artifacts: dict[str, Any] | Any, residuals: dict[str, float]
    ) -> None:
        for total_name, block_name in (
            ("reserve_shortfall", "reserve_shortfall_block"),
            ("reserve_shortfall_unit", "reserve_shortfall_unit_block"),
            ("reserve_shortfall_group", "reserve_shortfall_group_block"),
        ):
            total = artifacts[total_name]
            blocks = artifacts[block_name]
            for key in total:
                residuals[f"{total_name}:{key}"] = abs(
                    _value(total[key])
                    - sum(_value(blocks[*key, tranche]) for tranche in BLOCKS)
                )

    @staticmethod
    def _risk_residuals(
        case: ReserveCase,
        artifacts: dict[str, Any] | Any,
        residuals: dict[str, float],
    ) -> None:
        assert case.reserve is not None
        assert case.hvdc is not None
        assert case.network is not None
        data = case.reserve
        risk = artifacts["island_risk"]
        gen_risk = artifacts["generator_island_risk"]
        group_risk = artifacts["group_island_risk"]
        hvdc_gen_risk = artifacts["hvdc_generator_island_risk"]
        hvdc_manual_risk = artifacts["hvdc_manual_island_risk"]
        hvdc_received = artifacts["hvdc_received"]
        hvdc_flow = artifacts["hvdc_flow"]
        hvdc_loss = artifacts["hvdc_loss"]
        generation = artifacts["generation"]
        reserve = artifacts["reserve"]
        effective = artifacts["reserve_share_effective"]
        shortfall = artifacts["reserve_shortfall"]
        shortfall_unit = artifacts["reserve_shortfall_unit"]
        shortfall_group = artifacts["reserve_shortfall_group"]
        send_zero = artifacts["hvdc_send_zero_binary"]
        for island in data.islands:
            ca, dt, island_name = island
            expected_received = sum(
                -_value(hvdc_flow[link])
                for link in case.hvdc.links
                for *prefix, bus in case.hvdc.sending_bus
                if tuple(prefix) == link
                and (ca, dt, bus, island_name) in case.network.bus_island
            ) + sum(
                _value(hvdc_flow[link]) - _value(hvdc_loss[link])
                for link in case.hvdc.links
                for *prefix, bus in case.hvdc.receiving_bus
                if tuple(prefix) == link
                and (ca, dt, bus, island_name) in case.network.bus_island
            )
            residuals[f"hvdc_received:{island}"] = abs(
                _value(hvdc_received[island]) - expected_received
            )
            for reserve_class in RESERVE_CLASSES:
                for risk_class in HVDC_RISKS:
                    key = (*island, reserve_class, risk_class)
                    expected = data.risk_adjustment_factor.get(key, 0.0) * (
                        expected_received
                        - data.free_reserve.get(key, 0.0)
                        - (
                            data.hvdc_pole_ramp_up.get(key, 0.0)
                            if risk_class in CE_RISKS
                            else 0.0
                        )
                        + data.modulation_risk_class.get(
                            (ca, dt, risk_class), 0.0
                        )
                    ) - _optional_value(shortfall, key)
                    residuals[f"hvdc_risk:{key}"] = abs(
                        _value(risk[key]) - expected
                    )
                for risk_class in MANUAL_RISKS:
                    key = (*island, reserve_class, risk_class)
                    expected = data.risk_adjustment_factor.get(key, 0.0) * (
                        data.risk_minimum.get(key, 0.0)
                        - data.free_reserve.get(key, 0.0)
                    ) - _value(effective[key]) - _optional_value(shortfall, key)
                    residuals[f"manual_risk:{key}"] = abs(
                        _value(risk[key]) - expected
                    )
        for key in gen_risk:
            ca, dt, island, offer, reserve_class, risk_class = key
            total = _risk_offer_total(
                case, artifacts, ca, dt, offer, reserve_class, risk_class
            )
            expected = data.risk_adjustment_factor.get(
                (ca, dt, island, reserve_class, risk_class), 0.0
            ) * (
                total
                - data.secondary_risk_offer.get(
                    (ca, dt, offer, risk_class), 0.0
                )
                - data.free_reserve.get(
                    (ca, dt, island, reserve_class, risk_class), 0.0
                )
            ) - _value(
                effective[ca, dt, island, reserve_class, risk_class]
            ) - _optional_value(shortfall_unit, key)
            residuals[f"generator_risk:{key}"] = abs(
                _value(gen_risk[key]) - expected
            )
            residuals[f"generator_risk_envelope:{key}"] = max(
                0.0, _value(gen_risk[key]) - _value(risk[key[:3] + key[4:]])
            )
        for key in group_risk:
            ca, dt, island, group, reserve_class, risk_class = key
            offers = [
                offer
                for r_ca, r_dt, r_group, offer, r_risk in data.risk_group_offer
                if (r_ca, r_dt, r_group, r_risk)
                == (ca, dt, group, risk_class)
            ]
            gross = (
                sum(
                    _value(artifacts["branch_flow"][ca, dt, branch]) * factor
                    for (
                        f_ca,
                        f_dt,
                        f_group,
                        branch,
                        f_risk,
                    ), factor in data.directional_risk_factor.items()
                    if (f_ca, f_dt, f_group, f_risk)
                    == (ca, dt, group, risk_class)
                )
                + sum(
                    _value(reserve[ca, dt, offer, reserve_class, reserve_type])
                    for offer in offers
                    for reserve_type in RESERVE_TYPES
                )
                if (ca, dt, island, group, risk_class)
                in data.island_link_risk_group
                else sum(
                    _value(generation[ca, dt, offer])
                    + data.fk_band.get((ca, dt, offer), 0.0)
                    + sum(
                        _value(
                            reserve[
                                ca, dt, offer, reserve_class, reserve_type
                            ]
                        )
                        for reserve_type in RESERVE_TYPES
                    )
                    for offer in offers
                )
            )
            envelope = (ca, dt, island, reserve_class, risk_class)
            expected = data.risk_adjustment_factor.get(envelope, 0.0) * (
                gross
                - data.secondary_risk_group.get(
                    (ca, dt, group, risk_class), 0.0
                )
                - data.free_reserve.get(envelope, 0.0)
            ) - _value(effective[envelope]) - _optional_value(
                shortfall_group, key
            )
            residuals[f"group_risk:{key}"] = abs(
                _value(group_risk[key]) - expected
            )
            residuals[f"group_risk_envelope:{key}"] = max(
                0.0, _value(group_risk[key]) - _value(risk[envelope])
            )
        for key in hvdc_gen_risk:
            ca, dt, island, offer, reserve_class, risk_class = key
            envelope = (ca, dt, island, reserve_class, risk_class)
            gross = (
                _risk_offer_total(
                    case,
                    artifacts,
                    ca,
                    dt,
                    offer,
                    reserve_class,
                    risk_class,
                )
                + _value(hvdc_received[ca, dt, island])
                - data.hvdc_secondary_subtractor.get((ca, dt, island), 0.0)
                - data.free_reserve.get(envelope, 0.0)
                + data.modulation_risk_class.get((ca, dt, risk_class), 0.0)
            )
            expected = data.risk_adjustment_factor.get(envelope, 0.0) * gross
            expected -= _optional_value(shortfall_unit, key)
            expected -= data.big_m * _value(send_zero[ca, dt, island]) * max(
                0, len(data.islands) - 1
            )
            residuals[f"hvdc_secondary_generator_risk:{key}"] = abs(
                _value(hvdc_gen_risk[key]) - expected
            )
            residuals[f"hvdc_secondary_generator_envelope:{key}"] = max(
                0.0, _value(hvdc_gen_risk[key]) - _value(risk[envelope])
            )
        for key in hvdc_manual_risk:
            ca, dt, island, reserve_class, risk_class = key
            expected = data.risk_adjustment_factor.get(key, 0.0) * (
                data.risk_minimum.get(key, 0.0)
                - data.free_reserve.get(key, 0.0)
                + _value(hvdc_received[ca, dt, island])
                - data.hvdc_secondary_subtractor.get((ca, dt, island), 0.0)
                + data.modulation_risk_class.get((ca, dt, risk_class), 0.0)
            ) - _optional_value(shortfall, key)
            expected -= data.big_m * _value(send_zero[ca, dt, island]) * max(
                0, len(data.islands) - 1
            )
            residuals[f"hvdc_secondary_manual_risk:{key}"] = abs(
                _value(hvdc_manual_risk[key]) - expected
            )
            residuals[f"hvdc_secondary_manual_envelope:{key}"] = max(
                0.0, _value(hvdc_manual_risk[key]) - _value(risk[key])
            )

    @staticmethod
    def _sharing_residuals(
        case: ReserveCase,
        artifacts: dict[str, Any] | Any,
        residuals: dict[str, float],
        tolerance: float,
    ) -> None:
        assert case.reserve is not None
        data = case.reserve
        sent = artifacts["hvdc_sent"]
        sent_loss = artifacts["hvdc_sent_loss"]
        received = artifacts["reserve_share_received"]
        share_sent = artifacts["reserve_share_sent"]
        # Components not exported as artifacts are obtained from the named,
        # immutable model block only for their solved values; every RHS below
        # is reconstructed from normalized input data.
        model_block = sent.parent_block()
        reserve_sent = model_block.HVDCReserveSent
        reserve_loss = model_block.HVDCReserveLoss
        energy_lambda = artifacts["lambda_hvdc_energy"]
        reserve_lambda = artifacts["lambda_hvdc_reserve"]
        for island in data.islands:
            residuals[f"nmir_energy_lambda:{island}"] = abs(
                sum(_value(energy_lambda[*island, bp]) for bp in ENERGY_BREAKPOINTS)
                - 1.0
            )
            residuals[f"nmir_energy_flow:{island}"] = abs(
                _value(sent[island])
                - sum(
                    data.energy_breakpoint_flow[*island, bp]
                    * _value(energy_lambda[*island, bp])
                    for bp in ENERGY_BREAKPOINTS
                )
            )
            residuals[f"nmir_energy_loss:{island}"] = abs(
                _value(sent_loss[island])
                - sum(
                    data.energy_breakpoint_loss[*island, bp]
                    * _value(energy_lambda[*island, bp])
                    for bp in ENERGY_BREAKPOINTS
                )
            )
            active = [
                position
                for position, bp in enumerate(ENERGY_BREAKPOINTS)
                if _value(energy_lambda[*island, bp]) > tolerance
            ]
            residuals[f"nmir_energy_adjacency:{island}"] = _adjacency(active)
            for reserve_class in RESERVE_CLASSES:
                for direction in DIRECTIONS:
                    key = (*island, reserve_class, direction)
                    residuals[f"nmir_reserve_lambda:{key}"] = abs(
                        sum(
                            _value(reserve_lambda[*key, bp])
                            for bp in RESERVE_BREAKPOINTS
                        )
                        - 1.0
                    )
                    residuals[f"nmir_reserve_flow:{key}"] = abs(
                        _value(reserve_sent[key])
                        - sum(
                            data.reserve_breakpoint_flow[*island, bp]
                            * _value(reserve_lambda[*key, bp])
                            for bp in RESERVE_BREAKPOINTS
                        )
                    )
                    residuals[f"nmir_reserve_loss:{key}"] = abs(
                        _value(reserve_loss[key])
                        - sum(
                            data.reserve_breakpoint_loss[*island, bp]
                            * _value(reserve_lambda[*key, bp])
                            for bp in RESERVE_BREAKPOINTS
                        )
                    )
                    active = [
                        position
                        for position, bp in enumerate(RESERVE_BREAKPOINTS)
                        if _value(reserve_lambda[*key, bp]) > tolerance
                    ]
                    residuals[f"nmir_reserve_adjacency:{key}"] = _adjacency(active)
                    others = [
                        other
                        for other in data.islands
                        if other[:2] == island[:2] and other[2] != island[2]
                    ]
                    expected = (
                        sum(
                            _value(share_sent[*other, reserve_class, direction])
                            - _value(reserve_loss[*other, reserve_class, direction])
                            + _value(sent_loss[other])
                            for other in others
                        )
                        if direction == "forward"
                        else sum(
                            _value(share_sent[*other, reserve_class, direction])
                            for other in others
                        )
                        - _value(reserve_loss[key])
                        + _value(sent_loss[island])
                    )
                    residuals[f"reserve_share_received:{key}"] = abs(
                        _value(received[key]) - expected
                    )

    @staticmethod
    def _objective_residuals(
        case: ReserveCase,
        artifacts: dict[str, Any] | Any,
        residuals: dict[str, float],
    ) -> None:
        assert case.reserve is not None
        data = case.reserve
        reserve_block = artifacts["reserve_block"]
        share_penalty = artifacts["reserve_share_penalty"]
        shared_nfr = artifacts["shared_nfr"]
        shared_reserve = artifacts["shared_reserve"]
        effective_ce = artifacts["reserve_share_effective_ce"]
        effective_ece = artifacts["reserve_share_effective_ece"]
        economics = artifacts["system_cost"].parent_block().SystemCostByPeriod
        for period in case.periods:
            reserve_cost = sum(
                _value(reserve_block[key]) * data.reserve_block_price[key]
                for key in reserve_block
                if key[:2] == period
            )
            energy_cost = sum(
                _value(artifacts["generation_block"][key]) * case.offer_price[key]
                for key in case.offer_blocks
                if key[:2] == period
            )
            residuals[f"system_cost:{period}"] = abs(
                _value(economics[period]) - energy_cost - reserve_cost
            )
            expected_penalty = (
                1e-5
                * sum(
                    _value(shared_nfr[key]) for key in shared_nfr if key[:2] == period
                )
                + 2e-5
                * sum(
                    _value(shared_reserve[key])
                    for key in shared_reserve
                    if key[:2] == period
                )
                + 3e-5
                * sum(
                    _value(effective_ce[key]) + _value(effective_ece[key])
                    for key in effective_ce
                    if key[:2] == period
                )
            )
            residuals[f"sharing_penalty:{period}"] = abs(
                _value(share_penalty[period]) - expected_penalty
            )


def validate_reserve_price_finite_difference(
    outcome: HvdcSolveOutcome,
    key: tuple[str, ...],
    *,
    perturbation_mw: float = 1e-4,
    tolerance: float = 1e-5,
) -> ReservePriceCheck:
    """Perturb island reserve availability in the fixed RMIP and check its dual."""

    pricing = outcome.pricing_model
    source_constraint = pricing.artifacts["island_reserve_definition"][key]
    dual = float(pricing.model.dual[source_constraint])
    model = pricing.model.clone()
    constraint = model.find_component(source_constraint.name)
    if constraint is None:
        raise KeyError(f"pricing constraint not found: {source_constraint.name}")
    upper = _value(constraint.upper)
    constraint.set_value((constraint.lower, constraint.body, upper + perturbation_mw))
    result = HighsBackend().solve(
        model,
        SolverConfiguration(
            {
                "solver": "simplex",
                "primal_feasibility_tolerance": 1e-8,
                "dual_feasibility_tolerance": 1e-8,
                "random_seed": 0,
                "threads": 1,
            }
        ),
    )
    if not result.solution_loaded:
        raise ValueError("reserve-price perturbation solution was not loaded")
    objective = next(model.component_data_objects(pyo.Objective, active=True))
    finite_difference = (
        _value(objective) - outcome.pricing_snapshot.objective
    ) / perturbation_mw
    error = abs(dual - finite_difference)
    return ReservePriceCheck(
        key,
        perturbation_mw,
        dual,
        finite_difference,
        error,
        tolerance,
        error <= tolerance,
    )


def _adjacency(active: list[int]) -> float:
    return 0.0 if len(active) < 2 or all(b - a <= 1 for a, b in pairwise(active)) else 1.0


def _risk_offer_total(
    case: ReserveCase,
    artifacts: dict[str, Any] | Any,
    ca: str,
    dt: str,
    offer: str,
    reserve_class: str,
    _risk_class: str,
) -> float:
    assert case.reserve is not None
    data = case.reserve
    generation = artifacts["generation"]
    reserve = artifacts["reserve"]
    return (
        _value(generation[ca, dt, offer])
        + data.fk_band.get((ca, dt, offer), 0.0)
        + sum(
            _value(reserve[ca, dt, offer, reserve_class, reserve_type])
            for reserve_type in RESERVE_TYPES
        )
        + sum(
            _value(generation[ca, dt, secondary])
            + sum(
                _value(
                    reserve[ca, dt, secondary, reserve_class, reserve_type]
                )
                for reserve_type in RESERVE_TYPES
            )
            for p_ca, p_dt, primary, secondary in data.primary_secondary_offer
            if (p_ca, p_dt, primary) == (ca, dt, offer)
        )
    )


def _optional_value(component: Any, key: tuple[str, ...]) -> float:
    try:
        return _value(component[key])
    except KeyError:
        return 0.0


def _value(value: Any) -> float:
    evaluated = pyo.value(value, exception=False)
    return 0.0 if evaluated is None else float(evaluated)
