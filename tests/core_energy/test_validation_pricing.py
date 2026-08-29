from __future__ import annotations

from dataclasses import replace

import pyomo.environ as pyo
import pytest

from pyspd.architecture import ModelAssembler
from pyspd.core_energy import (
    CoreEnergyPricingEngine,
    CoreEnergySolvePolicy,
    core_energy_formulation,
)
from pyspd.core_energy.validation import finite_difference_price, validate_core_energy
from tests.core_energy.conftest import make_core_case


def test_independent_objective_residual_complementarity_and_finite_difference() -> None:
    data = make_core_case(
        load=75.0,
        offers=(("CHEAP", 50.0, 10.0), ("MARGINAL", 100.0, 20.0)),
        starts={"CHEAP": 50.0, "MARGINAL": 25.0},
        study_mode=130.0,
    )
    built = ModelAssembler().assemble(core_energy_formulation(), data)
    result = CoreEnergySolvePolicy().solve(built)
    prices = CoreEnergyPricingEngine().price(built, result)
    report = validate_core_energy(built, prices)
    assert report.maximum_residual <= 1e-8
    assert report.maximum_bound_violation <= 1e-8
    assert max(abs(value) for value in report.objective_component_errors.values()) <= 1e-8
    assert report.maximum_complementarity_error <= 1e-8
    assert report.objective_components == pytest.approx(
        {
            "system_cost": 1_000.0,
            "system_benefit": 0.0,
            "balance_penalty": 0.0,
            "ramp_penalty": 0.0,
            "movement_cost": 0.0,
            "scarcity_cost": 0.0,
            "system_penalty": 0.0,
            "net_benefit": -1_000.0,
        }
    )
    region = ("C1", "T1", "NI")
    assert prices.unit == "NZD/MWh"
    assert finite_difference_price(data, region) == pytest.approx(
        prices.values[region], abs=1e-5
    )
    assert pyo.value(built.artifacts["net_benefit"]) == pytest.approx(-1_000.0)


def test_infeasible_physics_is_optimal_with_explicit_balance_slack() -> None:
    data = make_core_case(load=120.0, offers=(("GEN", 100.0, 10.0),))
    built = ModelAssembler().assemble(core_energy_formulation(), data)
    result = CoreEnergySolvePolicy().solve(built)
    assert result.raw_termination_condition == "optimal"
    assert pyo.value(built.artifacts["balance_deficit"]["C1", "T1", "NI"]) == pytest.approx(
        20.0
    )
    prices = CoreEnergyPricingEngine().price(built, result)
    assert prices.values[("C1", "T1", "NI")] == pytest.approx(500_000.0)


def test_energy_scarcity_blocks_are_explicit_and_set_price() -> None:
    data = make_core_case(load=80.0, offers=(("GEN", 50.0, 10.0),))
    node = ("C1", "T1", "N1")
    scarcity_block = (*node, "t1")
    data = replace(
        data,
        nodes=frozenset({node}),
        node_region={node: ("C1", "T1", "NI")},
        scarcity_blocks=frozenset({scarcity_block}),
        scarcity_limit={scarcity_block: 100.0},
        scarcity_price={scarcity_block: 1_000.0},
        scarcity_enabled={("C1", "T1"): 1.0},
    )
    built = ModelAssembler().assemble(core_energy_formulation(), data)
    result = CoreEnergySolvePolicy().solve(built)
    prices = CoreEnergyPricingEngine().price(built, result)
    assert pyo.value(built.artifacts["energy_scarcity_block"][scarcity_block]) == 30.0
    assert prices.values[("C1", "T1", "NI")] == pytest.approx(1_000.0)
