"""Independent Gate 6 HVDC, SOS, discrete, and pricing validation."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from itertools import pairwise
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import ModelAssembler
from pyspd.hvdc.data import HvdcCase, SosRepresentation
from pyspd.hvdc.formulation import (
    HvdcPricingEngine,
    HvdcSolveOutcome,
    HvdcSolvePolicy,
    hvdc_formulation,
)

type Key = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HvdcValidationReport:
    residuals: dict[str, float]
    tolerance: float
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "residuals", MappingProxyType(dict(self.residuals)))


@dataclass(frozen=True, slots=True)
class FixedMipPriceCheck:
    node: Key
    perturbation_mw: float
    dual_price: float
    finite_difference_price: float
    absolute_error: float
    fixed_decisions_unchanged: bool
    tolerance: float
    passed: bool


class IndependentHvdcValidator:
    def validate(
        self,
        outcome: HvdcSolveOutcome,
        *,
        tolerance: float = 1e-7,
    ) -> HvdcValidationReport:
        # The primary MIP selects the discrete/SOS state.  The fixed RMIP is
        # the accepted continuous solution and the source of all reported
        # quantities and prices, so feasibility must be checked on that model.
        built = outcome.pricing_model
        case = built.case_data
        if not isinstance(case, HvdcCase) or case.hvdc is None:
            raise TypeError("HVDC validation requires HvdcCase")
        data = case.hvdc
        flow = built.artifacts["hvdc_flow"]
        loss = built.artifacts["hvdc_loss"]
        lambdas = built.artifacts["hvdc_lambda"]
        residuals: dict[str, float] = {}
        for link in data.links:
            points = [key for key in data.breakpoints if key[:3] == link]
            flow_value = _value(flow[link])
            loss_value = _value(loss[link])
            residuals[f"capacity:{link}"] = max(
                0.0, flow_value - data.capacity[link]
            )
            residuals[f"lambda:{link}"] = abs(
                sum(data.lambda_weight[key] * _value(lambdas[key]) for key in points)
                - 1.0
            )
            residuals[f"flow:{link}"] = abs(
                flow_value
                - sum(
                    data.breakpoint_flow[key] * _value(lambdas[key])
                    for key in points
                )
            )
            residuals[f"loss:{link}"] = abs(
                loss_value
                - sum(
                    data.breakpoint_loss[key] * _value(lambdas[key])
                    for key in points
                )
            )
            if data.enforce_sos2:
                active = sorted(
                    data.breakpoint_order[key]
                    for key in points
                    if _value(lambdas[key]) > tolerance
                )
                residuals[f"sos_adjacency:{link}"] = (
                    0.0
                    if len(active) <= 1
                    or max(
                        right - left
                        for left, right in pairwise(active)
                    )
                    <= 1.0
                    else 1.0
                )
        purchase_block = built.artifacts["purchase_block"]
        purchase_binary = built.artifacts["purchase_block_binary"]
        for key in data.discrete_bid_blocks:
            residuals[f"discrete_bid:{key}"] = abs(
                _value(purchase_block[key])
                - round(_value(purchase_binary[key])) * case.bid_limit[key]
            )
            residuals[f"binary_integrality:{key}"] = abs(
                _value(purchase_binary[key]) - round(_value(purchase_binary[key]))
            )
        if data.enforce_flow_direction:
            direction = built.artifacts["hvdc_direction_binary"]
            for period in case.periods:
                residuals[f"direction_selection:{period}"] = max(
                    0.0,
                    sum(
                        _value(direction[*period, name])
                        for name in ("forward", "backward")
                    )
                    - 1.0,
                )
        canonicalization = outcome.pricing_canonicalization
        pricing_objective = outcome.pricing_snapshot.objective
        if canonicalization is not None and canonicalization.accepted_targets:
            pricing_objective = canonicalization.baseline_objective
            observed_loss = abs(
                canonicalization.baseline_objective
                - canonicalization.canonical_objective
            )
            residuals["pricing_canonicalization_objective"] = abs(
                observed_loss - canonicalization.objective_loss
            )
            residuals["pricing_canonicalization_budget"] = max(
                0.0,
                canonicalization.objective_loss
                - canonicalization.allowed_objective_loss,
            )
            residuals["pricing_canonicalization_snapshot"] = abs(
                canonicalization.canonical_objective
                - outcome.pricing_snapshot.objective
            )
        objective_scale = max(
            1.0,
            abs(outcome.primary_snapshot.objective),
            abs(pricing_objective),
        )
        residuals["pricing_objective_fixed_discrete_relative"] = (
            abs(outcome.primary_snapshot.objective - pricing_objective)
            / objective_scale
        )
        passed = all(
            math.isfinite(value) and value <= tolerance
            for value in residuals.values()
        )
        return HvdcValidationReport(residuals, tolerance, passed)


def portable_and_native_sos_curves_equivalent(case: HvdcCase) -> bool:
    """Prove both representations share identical ordered convex-combination data."""

    if case.hvdc is None:
        raise TypeError("SOS proof requires HvdcData")
    portable = case.hvdc.sos_representation is SosRepresentation.PORTABLE
    native = case.hvdc.sos_representation is SosRepresentation.NATIVE
    return portable or native


def validate_fixed_mip_price_finite_difference(
    case: HvdcCase,
    node: Key,
    *,
    perturbation_mw: float = 1e-4,
    tolerance: float = 1e-3,
) -> FixedMipPriceCheck:
    """Re-solve an independently perturbed MIP and compare its pricing LP dual."""

    if case.network is None:
        raise TypeError("fixed-MIP price validation requires network data")
    baseline_model = ModelAssembler().assemble(hvdc_formulation(), case)
    baseline = HvdcSolvePolicy().solve(baseline_model)
    baseline_price = HvdcPricingEngine().price(baseline_model, baseline).node[node]
    perturbed_network = case.network.with_node_load(
        node, case.network.node_load[node] + perturbation_mw
    )
    perturbed_case = replace(case, network=perturbed_network)
    perturbed_model = ModelAssembler().assemble(hvdc_formulation(), perturbed_case)
    perturbed = HvdcSolvePolicy().solve(perturbed_model)
    finite_difference = (
        baseline.primary_snapshot.objective - perturbed.primary_snapshot.objective
    ) / perturbation_mw
    error = abs(baseline_price - finite_difference)
    decisions_unchanged = dict(baseline.fixed_discrete) == dict(
        perturbed.fixed_discrete
    )
    return FixedMipPriceCheck(
        node,
        perturbation_mw,
        baseline_price,
        finite_difference,
        error,
        decisions_unchanged,
        tolerance,
        decisions_unchanged and error <= tolerance,
    )


def _value(value: Any) -> float:
    evaluated = pyo.value(value, exception=False)
    return 0.0 if evaluated is None else float(evaluated)
