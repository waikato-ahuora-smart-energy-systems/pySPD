"""Independent residual, objective, complementarity, and price validation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuiltModel, ModelAssembler
from pyspd.core_energy.data import CoreEnergyCase, Region
from pyspd.core_energy.formulation import (
    CoreEnergyPrices,
    CoreEnergyPricingEngine,
    CoreEnergySolvePolicy,
    core_energy_formulation,
)


@dataclass(frozen=True, slots=True)
class CoreEnergyValidation:
    balance_residuals: Mapping[Region, float]
    ramp_up_violations: Mapping[tuple[str, ...], float]
    ramp_down_violations: Mapping[tuple[str, ...], float]
    objective_components: Mapping[str, float]
    objective_component_errors: Mapping[str, float]
    maximum_bound_violation: float
    maximum_complementarity_error: float

    def __post_init__(self) -> None:
        for name in (
            "balance_residuals",
            "ramp_up_violations",
            "ramp_down_violations",
            "objective_components",
            "objective_component_errors",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @property
    def maximum_residual(self) -> float:
        values = (
            *self.balance_residuals.values(),
            *self.ramp_up_violations.values(),
            *self.ramp_down_violations.values(),
        )
        return max((abs(value) for value in values), default=0.0)


def validate_core_energy(
    built: BuiltModel, prices: CoreEnergyPrices | None = None
) -> CoreEnergyValidation:
    """Recompute economics and feasibility without using Pyomo expressions."""

    data = built.case_data
    if not isinstance(data, CoreEnergyCase):
        raise TypeError("validation requires CoreEnergyCase")
    artifacts = built.artifacts
    generation = _values(artifacts["generation"])
    generation_block = _values(artifacts["generation_block"])
    purchase = _values(artifacts["purchase"])
    purchase_block = _values(artifacts["purchase_block"])
    deficit = _values(artifacts["balance_deficit"])
    surplus = _values(artifacts["balance_surplus"])
    ramp_deficit = _values(artifacts["ramp_deficit"])
    ramp_surplus = _values(artifacts["ramp_surplus"])
    up_delta = _values(artifacts["generation_up_delta"])
    down_delta = _values(artifacts["generation_down_delta"])

    balance_residuals = {
        region: sum(
            value
            for offer, value in generation.items()
            if data.offer_region[offer] == region
        )
        + deficit[region]
        - data.required_load[region]
        - sum(
            value
            for bid, value in purchase.items()
            if data.bid_region[bid] == region
        )
        - surplus[region]
        for region in data.regions
    }

    ramp_up_violations: dict[tuple[str, ...], float] = {}
    ramp_down_violations: dict[tuple[str, ...], float] = {}
    for offer in ramp_deficit:
        ca, dt, _name = offer
        total = generation[offer] + sum(
            generation[(map_ca, map_dt, secondary)]
            for map_ca, map_dt, primary, secondary in data.primary_secondary
            if (map_ca, map_dt, primary) == offer
        )
        ramp_up_violations[offer] = max(
            0.0,
            total
            - ramp_deficit[offer]
            - data.generation_start[offer]
            - data.ramp_rate_up[offer] * data.interval_minutes[(ca, dt)] / 60.0,
        )
        ramp_down_violations[offer] = max(
            0.0,
            data.generation_start[offer]
            - data.ramp_rate_down[offer] * data.interval_minutes[(ca, dt)] / 60.0
            - total
            - ramp_surplus[offer],
        )

    independent = {
        "system_cost": sum(
            generation_block[key] * data.offer_price[key]
            for key in data.offer_blocks
        ),
        "system_benefit": sum(
            purchase_block[key] * data.bid_price[key] for key in data.bid_blocks
        ),
        "balance_penalty": sum(
            data.balance_deficit_penalty * deficit[key]
            + data.balance_surplus_penalty * surplus[key]
            for key in data.regions
        ),
        "ramp_penalty": sum(
            data.ramp_deficit_penalty * ramp_deficit[key]
            + data.ramp_surplus_penalty * ramp_surplus[key]
            for key in ramp_deficit
        ),
        "movement_cost": data.movement_penalty
        * sum(up_delta[key] + down_delta[key] for key in up_delta),
    }
    independent["net_benefit"] = (
        independent["system_benefit"]
        - independent["system_cost"]
        - independent["balance_penalty"]
        - independent["ramp_penalty"]
        - independent["movement_cost"]
    )
    errors = {
        name: float(pyo.value(artifacts[name])) - value
        for name, value in independent.items()
    }
    bound_violation = max(
        (_bound_violation(variable) for variable in built.model.component_data_objects(pyo.Var)),
        default=0.0,
    )
    complementarity = (
        _complementarity_error(data, generation_block, purchase_block, prices)
        if prices is not None
        else math.nan
    )
    return CoreEnergyValidation(
        balance_residuals,
        ramp_up_violations,
        ramp_down_violations,
        independent,
        errors,
        bound_violation,
        complementarity,
    )


def finite_difference_price(
    data: CoreEnergyCase, region: Region, *, epsilon_mw: float = 1e-4
) -> float:
    """Calculate marginal supply cost by two independent complete builds."""

    if epsilon_mw <= 0.0:
        raise ValueError("epsilon_mw must be positive")
    formulation = core_energy_formulation()
    assembler = ModelAssembler()
    base = assembler.assemble(formulation, data)
    base_result = CoreEnergySolvePolicy().solve(base)
    base_value = float(pyo.value(base.artifacts["net_benefit"]))
    perturbed_data = data.with_required_load(
        region, data.required_load[region] + epsilon_mw
    )
    perturbed = assembler.assemble(formulation, perturbed_data)
    CoreEnergySolvePolicy().solve(perturbed)
    perturbed_value = float(pyo.value(perturbed.artifacts["net_benefit"]))
    # Retain pricing as an independent dual check and fail if suffix loading is bad.
    CoreEnergyPricingEngine().price(base, base_result)
    return (base_value - perturbed_value) / epsilon_mw


def _values(component: Any) -> dict[tuple[str, ...], float]:
    return {
        tuple(index): float(pyo.value(component[index]))
        for index in component
    }


def _bound_violation(variable: Any) -> float:
    value = float(pyo.value(variable))
    lower = None if variable.lb is None else float(pyo.value(variable.lb))
    upper = None if variable.ub is None else float(pyo.value(variable.ub))
    return max(
        0.0,
        0.0 if lower is None else lower - value,
        0.0 if upper is None else value - upper,
    )


def _complementarity_error(
    data: CoreEnergyCase,
    generation: Mapping[tuple[str, ...], float],
    purchases: Mapping[tuple[str, ...], float],
    prices: CoreEnergyPrices,
    tolerance: float = 1e-7,
) -> float:
    errors: list[float] = []
    for block, value in generation.items():
        price = prices.values[data.offer_region[block[:3]]]
        cost = data.offer_price[block]
        limit = data.offer_limit[block]
        if value <= tolerance:
            errors.append(max(0.0, price - cost))
        elif value >= limit - tolerance:
            errors.append(max(0.0, cost - price))
        else:
            errors.append(abs(cost - price))
    for block, value in purchases.items():
        limit = data.bid_limit[block]
        if limit < 0.0:
            continue
        price = prices.values[data.bid_region[block[:3]]]
        benefit = data.bid_price[block]
        if value <= tolerance:
            errors.append(max(0.0, benefit - price))
        elif value >= limit - tolerance:
            errors.append(max(0.0, price - benefit))
        else:
            errors.append(abs(benefit - price))
    return max(errors, default=0.0)
