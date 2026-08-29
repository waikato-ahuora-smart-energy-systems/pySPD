from __future__ import annotations

import pyomo.environ as pyo
import pytest

from pyspd.architecture import ModelAssembler
from pyspd.network import (
    IndependentNetworkValidator,
    NetworkPricingEngine,
    NetworkSolvePolicy,
    ac_network_formulation,
    validate_nodal_price_finite_difference,
)
from tests.network.conftest import make_network_case


def solve(case):
    built = ModelAssembler().assemble(ac_network_formulation(), case)
    result = NetworkSolvePolicy().solve(built)
    prices = NetworkPricingEngine().price(built, result)
    report = IndependentNetworkValidator().validate(built, prices)
    assert report.passed, report.residuals
    return built, prices, report


def test_two_bus_uncongested_dc_flow_and_prices() -> None:
    built, prices, _report = solve(make_network_case())
    assert pyo.value(built.artifacts["branch_flow"]["C1", "T1", "L1"]) == pytest.approx(50.0)
    assert prices.bus[("C1", "T1", "B1")] == pytest.approx(10.0)
    assert prices.bus[("C1", "T1", "B2")] == pytest.approx(10.0)
    assert prices.node[("C1", "T1", "N2")] == pytest.approx(10.0)


def test_congestion_separates_nodal_prices_without_capacity_violation() -> None:
    built, prices, report = solve(make_network_case(capacity=30.0))
    assert pyo.value(built.artifacts["branch_flow"]["C1", "T1", "L1"]) == pytest.approx(30.0)
    assert pyo.value(built.artifacts["balance_deficit"]["C1", "T1", "B2"]) == pytest.approx(20.0)
    assert prices.bus[("C1", "T1", "B2")] > prices.bus[("C1", "T1", "B1")]
    assert report.rentals[("C1", "T1", "L1")] > 0.0


def test_reverse_flow_uses_backward_direction() -> None:
    built, _prices, _report = solve(
        make_network_case(generation_bus="B2", load_bus="B1")
    )
    assert pyo.value(built.artifacts["branch_flow"]["C1", "T1", "L1"]) == pytest.approx(-50.0)
    assert pyo.value(
        built.artifacts["directed_branch_flow"]["C1", "T1", "L1", "backward"]
    ) == pytest.approx(50.0)


def test_disconnected_topology_is_balanced_locally_and_prices_dead_end() -> None:
    built, prices, _report = solve(make_network_case(connected=False))
    assert len(built.artifacts["branch_flow"]) == 0
    assert pyo.value(built.artifacts["balance_deficit"]["C1", "T1", "B2"]) == pytest.approx(50.0)
    assert prices.bus[("C1", "T1", "B2")] == pytest.approx(500_000.0)


def test_piecewise_losses_and_fixed_loss_allocation() -> None:
    built, prices, _report = solve(
        make_network_case(
            fixed_loss=2.0,
            loss_segments=(("ls1", 20.0, 0.05), ("ls2", 100.0, 0.10)),
        )
    )
    flow = pyo.value(built.artifacts["branch_flow"]["C1", "T1", "L1"])
    loss = pyo.value(
        built.artifacts["directed_branch_loss"]["C1", "T1", "L1", "forward"]
    )
    assert flow == pytest.approx(55.5555555556)
    assert loss == pytest.approx(4.5555555556)
    assert prices.bus[("C1", "T1", "B2")] > prices.bus[("C1", "T1", "B1")]


def test_all_security_constraint_senses_bind_or_remain_slack() -> None:
    case = make_network_case(
        branch_constraints=(
            ("LE", -1.0, 60.0, 1.0),
            ("GE", 1.0, 40.0, 1.0),
            ("EQ", 0.0, 50.0, 1.0),
        ),
        market_constraints=(
            ("MLE", -1.0, 60.0, 1.0),
            ("MGE", 1.0, 40.0, 1.0),
            ("MEQ", 0.0, 50.0, 1.0),
        ),
    )
    built, _prices, _report = solve(case)
    assert len(built.artifacts["branch_security_le"]) == 1
    assert len(built.artifacts["branch_security_ge"]) == 1
    assert len(built.artifacts["branch_security_eq"]) == 1
    assert len(built.artifacts["market_node_security_le"]) == 1
    assert len(built.artifacts["market_node_security_ge"]) == 1
    assert len(built.artifacts["market_node_security_eq"]) == 1


def test_nodal_price_matches_independent_objective_perturbation() -> None:
    check = validate_nodal_price_finite_difference(
        make_network_case(), ("C1", "T1", "N2")
    )
    assert check.passed
    assert check.reported_price == pytest.approx(10.0)
