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
from tests.core_energy.conftest import make_core_case


def solve(data):
    built = ModelAssembler().assemble(core_energy_formulation(), data)
    result = CoreEnergySolvePolicy().solve(built)
    prices = CoreEnergyPricingEngine().price(built, result)
    return built, prices


@pytest.mark.parametrize(
    ("offers", "load", "expected", "objective", "price"),
    [
        (
            (("CHEAP", 50.0, 10.0), ("DEAR", 50.0, 20.0)),
            75.0,
            {"CHEAP": 50.0, "DEAR": 25.0},
            -1_000.0,
            20.0,
        ),
        ((("ZERO", 100.0, 0.0),), 50.0, {"ZERO": 50.0}, 0.0, 0.0),
    ],
)
def test_analytic_merit_negative_and_zero_price(
    offers, load, expected, objective, price
) -> None:
    built, prices = solve(make_core_case(load=load, offers=offers))
    generation = built.artifacts["generation"]
    for name, value in expected.items():
        assert pyo.value(generation["C1", "T1", name]) == pytest.approx(value)
    assert pyo.value(built.artifacts["net_benefit"]) == pytest.approx(objective)
    assert prices.values[("C1", "T1", "NI")] == pytest.approx(price)


def test_analytic_negative_price_with_vspd_nonnegative_system_cost() -> None:
    data = make_core_case(
        load=100.0,
        offers=(("MUST_RUN", 50.0, 100.0), ("NEG", 100.0, -20.0)),
        starts={"MUST_RUN": 50.0, "NEG": 0.0},
        ramp_down={"MUST_RUN": 0.0},
        study_mode=101.0,
    )
    built, prices = solve(replace(data, movement_penalty=0.0))
    assert pyo.value(built.artifacts["generation"]["C1", "T1", "MUST_RUN"]) == 50.0
    assert pyo.value(built.artifacts["generation"]["C1", "T1", "NEG"]) == 50.0
    assert pyo.value(built.artifacts["net_benefit"]) == pytest.approx(-4_000.0)
    assert prices.values[("C1", "T1", "NI")] == pytest.approx(-20.0)


def test_price_sensitive_demand_and_capacity() -> None:
    built, prices = solve(
        make_core_case(
            load=20.0,
            offers=(("GEN", 100.0, 30.0),),
            bids=(("LOAD", 50.0, 50.0),),
        )
    )
    assert pyo.value(built.artifacts["purchase"]["C1", "T1", "LOAD"]) == pytest.approx(
        50.0
    )
    assert pyo.value(built.artifacts["generation"]["C1", "T1", "GEN"]) == pytest.approx(
        70.0
    )
    assert prices.values[("C1", "T1", "NI")] == pytest.approx(30.0)


def test_negative_demand_bid_uses_vspd_signed_bounds() -> None:
    built, _prices = solve(
        make_core_case(
            load=20.0,
            offers=(("GEN", 100.0, 30.0),),
            bids=(("EXPORT", -10.0, 100.0),),
        )
    )
    purchase = built.artifacts["purchase_block"]["C1", "T1", "EXPORT", "1"]
    assert purchase.lb == -10.0
    assert purchase.ub == 0.0
