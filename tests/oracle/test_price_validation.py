from __future__ import annotations

import pytest

from tools.oracle.price_validation import (
    FiniteDifferenceCheck,
    IndependentPriceValidator,
    NodeBusAllocation,
    NodePriceMapper,
    PriceComparator,
)


def test_node_price_mapper_reproduces_allocation_weighted_price() -> None:
    prices = NodePriceMapper().map_prices(
        bus_prices={"B1": 100.0, "B2": 120.0},
        allocations=(
            NodeBusAllocation("N1", "B1", 0.25),
            NodeBusAllocation("N1", "B2", 0.75),
            NodeBusAllocation("N2", "B1", 1.0),
        ),
    )

    assert prices == {"N1": 115.0, "N2": 100.0}


def test_node_price_mapper_rejects_invalid_allocation_sum() -> None:
    with pytest.raises(ValueError, match="allocation factors"):
        NodePriceMapper().map_prices(
            bus_prices={"B1": 100.0},
            allocations=(NodeBusAllocation("N1", "B1", 0.9),),
        )


def test_central_finite_difference_validates_max_net_benefit_price() -> None:
    check = FiniteDifferenceCheck.for_maximum_net_benefit(
        objective_minus=1000.5,
        objective_plus=999.5,
        perturbation_mw=0.01,
        expected_price=50.0,
        absolute_tolerance=1e-8,
    )

    assert check.observed_price == pytest.approx(50.0)
    assert check.passed


def test_price_comparator_requires_exact_keys_and_reports_worst_delta() -> None:
    comparison = PriceComparator.compare(
        actual={("base", "N1"): 50.001, ("base", "N2"): 60.0},
        expected={("base", "N1"): 50.0, ("base", "N2"): 60.0},
        absolute_tolerance=0.0011,
        relative_tolerance=0.0,
    )

    assert comparison.passed
    assert comparison.max_absolute_delta == pytest.approx(0.001)
    assert comparison.worst_key == ("base", "N1")

    with pytest.raises(ValueError, match="price keys"):
        PriceComparator.compare(
            actual={("base", "N1"): 50.0},
            expected={("base", "N2"): 50.0},
        )


def test_independent_validator_maps_equation_marginals_to_native_and_csv_prices() -> (
    None
):
    result = IndependentPriceValidator().validate(
        bus_marginals={("case", "period", "B1"): 50.0},
        allocations={("case", "period", "N1", "B1"): 1.0},
        native_prices={("case", "period", "base", "N1"): 50.0},
        active_scenario="base",
        report_prices={("period", "base", "N1"): 50.0},
        native_absolute_tolerance=1e-10,
        report_absolute_tolerance=0.0005,
    )

    assert result.passed
    assert result.price_count == 1
    assert result.native_comparison.max_absolute_delta == pytest.approx(0.0)
    assert result.report_comparison.max_absolute_delta == pytest.approx(0.0)


def test_independent_validator_accepts_explicit_postprocessed_bus_prices() -> None:
    result = IndependentPriceValidator().validate(
        bus_marginals={
            ("case", "period", "B1"): 50.0,
            ("case", "period", "B_DEAD"): -500_000.0,
        },
        mapped_bus_prices={
            ("case", "period", "B1"): 50.0,
            ("case", "period", "B_DEAD"): 0.0,
        },
        allocations={
            ("case", "period", "N1", "B1"): 1.0,
            ("case", "period", "N_DEAD", "B_DEAD"): 1.0,
        },
        native_prices={
            ("case", "period", "normal", "N1"): 50.0,
            ("case", "period", "normal", "N_DEAD"): 0.0,
        },
        active_scenario="normal",
        report_prices={
            ("period", "normal", "N1"): 50.0,
            ("period", "normal", "N_DEAD"): 0.0,
        },
        bus_price_adjustment_count=1,
    )

    assert result.passed
    assert result.price_count == 2
    assert result.bus_price_adjustment_count == 1
