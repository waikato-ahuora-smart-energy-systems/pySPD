from __future__ import annotations

from dataclasses import replace

import pyomo.environ as pyo
import pytest
from pyomo.repn.standard_repn import generate_standard_repn

from pyspd.architecture import ModelAssembler
from pyspd.network import (
    IndependentNetworkValidator,
    NetworkPricingEngine,
    NetworkSolvePolicy,
    ac_network_formulation,
    validate_nodal_price_finite_difference,
)
from tests.network.conftest import make_network_case, make_three_bus_case


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
    assert prices.bus_price_intervals == {}
    assert prices.node_price_intervals == {}


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


def test_three_bus_line_preserves_flow_and_price_across_both_edges() -> None:
    built, prices, _report = solve(make_three_bus_case())
    for branch in ("L1", "L2"):
        assert pyo.value(
            built.artifacts["branch_flow"]["C1", "T1", branch]
        ) == pytest.approx(50.0)
    assert prices.bus[("C1", "T1", "B1")] == pytest.approx(10.0)
    assert prices.bus[("C1", "T1", "B3")] == pytest.approx(10.0)


def test_disconnected_topology_is_balanced_locally_and_prices_dead_end() -> None:
    built, prices, _report = solve(make_network_case(connected=False))
    assert len(built.artifacts["branch_flow"]) == 0
    assert pyo.value(built.artifacts["balance_deficit"]["C1", "T1", "B2"]) == pytest.approx(50.0)
    assert prices.bus[("C1", "T1", "B2")] == pytest.approx(500_000.0)


def test_missing_sparse_node_bus_allocation_is_treated_as_zero() -> None:
    case = make_network_case()
    assert case.network is not None
    missing = ("C1", "T1", "N1", "B1")
    case = replace(
        case,
        network=replace(
            case.network,
            node_bus_allocation={
                key: value
                for key, value in case.network.node_bus_allocation.items()
                if key != missing
            },
        ),
    )

    built = ModelAssembler().assemble(ac_network_formulation(), case)
    balance = built.artifacts["energy_balance"]["C1", "T1", "B1"]
    representation = generate_standard_repn(balance.body)

    assert representation.nonlinear_expr is None


def test_dead_node_is_classified_from_electrical_island_status() -> None:
    case = make_network_case()
    assert case.network is not None
    case = replace(
        case,
        network=replace(
            case.network,
            bus_electrical_island={
                **case.network.bus_electrical_island,
                ("C1", "T1", "B2"): 0.0,
            },
        ),
    )
    _built, prices, _report = solve(case)
    assert ("C1", "T1", "N2") in prices.dead_nodes
    assert prices.node[("C1", "T1", "N2")] == 0.0


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


@pytest.mark.parametrize(
    ("active_bus", "passive_leaf"), (("B1", "B2"), ("B2", "B1"))
)
def test_zero_flow_loss_branch_uses_cplex_export_subgradient(
    active_bus: str, passive_leaf: str
) -> None:
    case = make_network_case(
        generation_bus=active_bus,
        load_bus=active_bus,
        loss_segments=(("ls1", 100.0, 0.001),),
    )
    built, prices, _report = solve(case)

    domains = built.artifacts["network_domains"]
    assert list(domains.DirectedACBranch) == [
        ("C1", "T1", "L1", "forward"),
        ("C1", "T1", "L1", "backward"),
    ]
    assert list(domains.ACLossSegment) == [
        ("C1", "T1", "L1", "ls1", "forward"),
        ("C1", "T1", "L1", "ls1", "backward"),
    ]
    assert prices.bus[("C1", "T1", active_bus)] == pytest.approx(10.0)
    assert prices.bus[("C1", "T1", passive_leaf)] == pytest.approx(10.0 * 0.999)
    assert prices.raw_bus_duals[("C1", "T1", passive_leaf)] == pytest.approx(
        10.0 * 0.999
    )
    expected_interval = (10.0 * 0.999, 10.0 / 0.999)
    leaf_node = ("C1", "T1", f"N{passive_leaf[-1]}")
    assert prices.bus_price_intervals[("C1", "T1", passive_leaf)] == pytest.approx(
        expected_interval
    )
    assert prices.node_price_intervals[leaf_node] == pytest.approx(expected_interval)
    load_derivative = validate_nodal_price_finite_difference(case, leaf_node)
    assert load_derivative.finite_difference_price == pytest.approx(10.0 / 0.999)
    assert not load_derivative.passed


def test_zero_flow_cplex_subgradient_propagates_through_transformer_tree() -> None:
    case = make_three_bus_case()
    assert case.network is not None
    period = ("C1", "T1")
    lossy = (*period, "L1")
    transformer = (*period, "L2")
    network = replace(
        case.network,
        node_load={
            (*period, "N1"): 50.0,
            (*period, "N2"): 0.0,
            (*period, "N3"): 0.0,
        },
        ac_loss_segment_factor={
            (*lossy, "ls1", direction): 0.001
            for direction in ("forward", "backward")
        }
        | {
            (*transformer, "ls1", direction): 0.0
            for direction in ("forward", "backward")
        },
    )

    built, prices, _report = solve(replace(case, network=network))

    assert pyo.value(built.artifacts["branch_flow"][lossy]) == pytest.approx(0.0)
    assert pyo.value(built.artifacts["branch_flow"][transformer]) == pytest.approx(
        0.0
    )
    expected = 10.0 * 0.999
    assert prices.bus[(*period, "B2")] == pytest.approx(expected)
    assert prices.bus[(*period, "B3")] == pytest.approx(expected)
    expected_interval = (expected, 10.0 / 0.999)
    assert prices.bus_price_intervals[(*period, "B2")] == pytest.approx(
        expected_interval
    )
    assert prices.bus_price_intervals[(*period, "B3")] == pytest.approx(
        expected_interval
    )


def test_zero_flow_export_subgradient_propagates_through_lossy_tree() -> None:
    case = make_three_bus_case()
    assert case.network is not None
    period = ("C1", "T1")
    network = replace(
        case.network,
        node_load={
            (*period, "N1"): 50.0,
            (*period, "N2"): 0.0,
            (*period, "N3"): 0.0,
        },
        ac_loss_segment_factor={
            (*branch, "ls1", direction): 0.001
            for branch in ((*period, "L1"), (*period, "L2"))
            for direction in ("forward", "backward")
        },
    )

    _built, prices, _report = solve(replace(case, network=network))

    assert prices.bus[(*period, "B2")] == pytest.approx(10.0 * 0.999)
    assert prices.bus[(*period, "B3")] == pytest.approx(10.0 * 0.999**2)
    assert prices.bus_price_intervals[(*period, "B3")] == pytest.approx(
        (10.0 * 0.999**2, 10.0 / 0.999**2)
    )


def test_zero_flow_interval_uses_each_directional_loss_factor() -> None:
    case = make_network_case(
        generation_bus="B1",
        load_bus="B1",
        loss_segments=(("ls1", 100.0, 0.001),),
    )
    assert case.network is not None
    branch = ("C1", "T1", "L1", "ls1")
    network = replace(
        case.network,
        ac_loss_segment_factor={
            (*branch, "forward"): 0.002,
            (*branch, "backward"): 0.001,
        },
    )

    _built, prices, _report = solve(replace(case, network=network))

    leaf = ("C1", "T1", "B2")
    assert prices.bus[leaf] == pytest.approx(10.0 * 0.999)
    assert prices.bus_price_intervals[leaf] == pytest.approx(
        (10.0 * 0.999, 10.0 / 0.998)
    )


def test_zero_flow_transit_bus_intersects_live_boundary_intervals() -> None:
    case = make_three_bus_case()
    assert case.network is not None
    period = ("C1", "T1")
    factors = {
        (*period, "L1", "ls1", direction): 0.01
        for direction in ("forward", "backward")
    } | {
        (*period, "L2", "ls1", direction): 0.005
        for direction in ("forward", "backward")
    }
    case = replace(
        case,
        network=replace(case.network, ac_loss_segment_factor=factors),
    )
    built = ModelAssembler().assemble(ac_network_formulation(), case)
    result = NetworkSolvePolicy().solve(built)
    assert result.solution_loaded
    for branch in built.artifacts["branch_flow"]:
        built.artifacts["branch_flow"][branch].set_value(0.0)
    for branch_direction in built.artifacts["directed_branch_flow"]:
        built.artifacts["directed_branch_flow"][branch_direction].set_value(0.0)

    center = (*period, "B2")
    candidate_prices = {
        (*period, "B1"): 100.0,
        center: 100.7,
        (*period, "B3"): 100.5,
    }
    intervals = NetworkPricingEngine._zero_flow_leaf_prices(
        built, case, candidate_prices
    )

    assert candidate_prices[center] == 100.7
    assert intervals[center] == pytest.approx(
        (100.5 * 0.995, 100.5 / 0.995)
    )


def test_zero_flow_transit_bus_empty_boundary_intersection_fails_closed() -> None:
    case = make_three_bus_case()
    assert case.network is not None
    factors = {
        (*branch, "ls1", direction): 0.001
        for branch in (("C1", "T1", "L1"), ("C1", "T1", "L2"))
        for direction in ("forward", "backward")
    }
    case = replace(
        case,
        network=replace(case.network, ac_loss_segment_factor=factors),
    )
    built = ModelAssembler().assemble(ac_network_formulation(), case)
    result = NetworkSolvePolicy().solve(built)
    assert result.solution_loaded
    for branch in built.artifacts["branch_flow"]:
        built.artifacts["branch_flow"][branch].set_value(0.0)
    for branch_direction in built.artifacts["directed_branch_flow"]:
        built.artifacts["directed_branch_flow"][branch_direction].set_value(0.0)

    center = ("C1", "T1", "B2")
    candidate_prices = {
        ("C1", "T1", "B1"): 100.0,
        center: 110.0,
        ("C1", "T1", "B3"): 120.0,
    }
    intervals = NetworkPricingEngine._zero_flow_leaf_prices(
        built, case, candidate_prices
    )

    assert candidate_prices[center] == 110.0
    assert center not in intervals


def test_zero_flow_tree_intersects_parallel_root_boundaries() -> None:
    case = make_three_bus_case()
    assert case.network is not None
    period = ("C1", "T1")
    parallel = (*period, "L3")
    branches = case.network.branches | {parallel}
    loss_segments = case.network.valid_ac_loss_segments | {
        (*parallel, "ls1", direction)
        for direction in ("forward", "backward")
    }
    factors = {
        (*period, "L1", "ls1", direction): 0.01
        for direction in ("forward", "backward")
    } | {
        (*period, "L2", "ls1", direction): 0.0
        for direction in ("forward", "backward")
    } | {
        (*parallel, "ls1", direction): 0.005
        for direction in ("forward", "backward")
    }
    network = replace(
        case.network,
        branches=branches,
        ac_branches=branches,
        branch_from_bus=case.network.branch_from_bus | {(*parallel, "B1")},
        branch_to_bus=case.network.branch_to_bus | {(*parallel, "B2")},
        branch_bus_connect=case.network.branch_bus_connect
        | {(*parallel, "B1"), (*parallel, "B2")},
        valid_ac_loss_segments=loss_segments,
        node_load={
            (*period, "N1"): 50.0,
            (*period, "N2"): 0.0,
            (*period, "N3"): 0.0,
        },
        branch_capacity=case.network.branch_capacity
        | {
            (*parallel, direction): 100.0
            for direction in ("forward", "backward")
        },
        branch_susceptance=case.network.branch_susceptance | {parallel: 100.0},
        branch_fixed_loss=case.network.branch_fixed_loss | {parallel: 0.0},
        ac_loss_segment_mw=case.network.ac_loss_segment_mw
        | {
            (*parallel, "ls1", direction): 100.0
            for direction in ("forward", "backward")
        },
        ac_loss_segment_factor=factors,
    )

    built, prices, _report = solve(replace(case, network=network))

    root = (*period, "B2")
    child = (*period, "B3")
    for branch in ("L1", "L2", "L3"):
        assert pyo.value(
            built.artifacts["branch_flow"][*period, branch]
        ) == pytest.approx(0.0, abs=1e-8)
    expected = (10.0 * 0.995, 10.0 / 0.995)
    assert prices.bus[root] == prices.raw_bus_duals[root]
    assert prices.bus[child] == prices.raw_bus_duals[child]
    assert prices.bus_price_intervals[root] == pytest.approx(expected)
    assert prices.bus_price_intervals[child] == pytest.approx(expected)


def test_loss_segment_boundary_and_reverse_direction_are_exact() -> None:
    segments = (("ls1", 20.0, 0.05), ("ls2", 100.0, 0.10))
    forward, _prices, _report = solve(
        make_network_case(load=19.0, loss_segments=segments)
    )
    assert pyo.value(
        forward.artifacts["branch_flow_block"][
            "C1", "T1", "L1", "ls1", "forward"
        ]
    ) == pytest.approx(20.0)
    assert pyo.value(
        forward.artifacts["branch_flow_block"][
            "C1", "T1", "L1", "ls2", "forward"
        ]
    ) == pytest.approx(0.0)
    reverse, _prices, _report = solve(
        make_network_case(
            load=19.0,
            generation_bus="B2",
            load_bus="B1",
            loss_segments=segments,
        )
    )
    assert pyo.value(
        reverse.artifacts["branch_flow_block"][
            "C1", "T1", "L1", "ls1", "backward"
        ]
    ) == pytest.approx(20.0)


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


@pytest.mark.parametrize(
    ("sense", "limit", "slack_name", "expected_slack"),
    [
        (-1.0, 60.0, "branch_constraint_surplus", 0.0),
        (-1.0, 50.0, "branch_constraint_surplus", 0.0),
        (-1.0, 30.0, "branch_constraint_surplus", 20.0),
        (1.0, 40.0, "branch_constraint_deficit", 0.0),
        (1.0, 50.0, "branch_constraint_deficit", 0.0),
        (1.0, 70.0, "branch_constraint_deficit", 20.0),
        (0.0, 50.0, "branch_constraint_deficit", 0.0),
        (0.0, 60.0, "branch_constraint_deficit", 10.0),
        (0.0, 40.0, "branch_constraint_surplus", 10.0),
    ],
)
def test_branch_security_binding_nonbinding_and_violated_with_slack(
    sense, limit, slack_name, expected_slack
) -> None:
    case = make_network_case(
        branch_constraints=(("C", sense, limit, 1.0),)
    )
    assert case.network is not None
    case = replace(
        case,
        network=replace(
            case.network,
            branch_constraint_deficit_penalty=1.0,
            branch_constraint_surplus_penalty=1.0,
        ),
    )
    built, _prices, _report = solve(case)
    assert pyo.value(built.artifacts[slack_name]["C1", "T1", "C"]) == pytest.approx(
        expected_slack
    )


@pytest.mark.parametrize(
    ("sense", "limit", "slack_name", "expected_slack"),
    [
        (-1.0, 60.0, "market_node_constraint_surplus", 0.0),
        (-1.0, 50.0, "market_node_constraint_surplus", 0.0),
        (-1.0, 30.0, "market_node_constraint_surplus", 20.0),
        (1.0, 40.0, "market_node_constraint_deficit", 0.0),
        (1.0, 50.0, "market_node_constraint_deficit", 0.0),
        (1.0, 70.0, "market_node_constraint_deficit", 20.0),
        (0.0, 50.0, "market_node_constraint_deficit", 0.0),
        (0.0, 60.0, "market_node_constraint_deficit", 10.0),
        (0.0, 40.0, "market_node_constraint_surplus", 10.0),
    ],
)
def test_market_node_security_binding_nonbinding_and_violated_with_slack(
    sense, limit, slack_name, expected_slack
) -> None:
    case = make_network_case(
        market_constraints=(("C", sense, limit, 1.0),)
    )
    assert case.network is not None
    case = replace(
        case,
        network=replace(
            case.network,
            market_node_deficit_penalty=1.0,
            market_node_surplus_penalty=1.0,
        ),
    )
    built, _prices, _report = solve(case)
    assert pyo.value(built.artifacts[slack_name]["C1", "T1", "C"]) == pytest.approx(
        expected_slack
    )


def test_market_node_bid_factor_is_present_with_exact_sign() -> None:
    case = make_network_case(
        load=0.0,
        bid_limit=20.0,
        market_constraints=(("BID_FACTOR", -1.0, 100.0, 1.0),),
    )
    assert case.network is not None
    case = replace(
        case,
        network=replace(
            case.network,
            market_node_energy_offer_factor={},
            market_node_energy_bid_factor={
                ("C1", "T1", "BID_FACTOR", "BID"): -1.5
            },
        ),
    )
    built = ModelAssembler().assemble(ac_network_formulation(), case)
    constraint = built.artifacts["market_node_security_le"][
        "C1", "T1", "BID_FACTOR"
    ]
    repn = generate_standard_repn(constraint.body)
    bid_coefficient = next(
        float(coefficient)
        for variable, coefficient in zip(
            repn.linear_vars, repn.linear_coefs, strict=True
        )
        if variable.parent_component().name == "DemandBids.Purchase"
    )
    assert bid_coefficient == -1.5


def test_market_node_constraint_retains_positive_offer_outside_valid_grid() -> None:
    case = make_network_case(market_constraints=(("ORPHAN_FACTOR", -1.0, 100.0, 1.0),))
    assert case.network is not None
    orphan = ("C1", "T1", "ORPHAN")
    case = replace(
        case,
        generation_offers=case.generation_offers | {orphan},
        generation_start={**case.generation_start, orphan: 0.0},
        network=replace(
            case.network,
            positive_offers=case.network.positive_offers | {orphan},
            market_node_energy_offer_factor={
                **case.network.market_node_energy_offer_factor,
                (*orphan[:2], "ORPHAN_FACTOR", orphan[2]): -2.0,
            },
        ),
    )

    built = ModelAssembler().assemble(ac_network_formulation(), case)

    generation = built.artifacts["generation"]
    assert orphan in generation
    assert generation[orphan].ub is None
    assert orphan not in built.artifacts["generation_definition"]
    constraint = built.artifacts["market_node_security_le"]["C1", "T1", "ORPHAN_FACTOR"]
    repn = generate_standard_repn(constraint.body)
    coefficient = next(
        float(value)
        for variable, value in zip(repn.linear_vars, repn.linear_coefs, strict=True)
        if variable.index() == orphan
    )
    assert coefficient == -2.0


def test_nodal_price_matches_independent_objective_perturbation() -> None:
    check = validate_nodal_price_finite_difference(
        make_network_case(), ("C1", "T1", "N2")
    )
    assert check.passed
    assert check.reported_price == pytest.approx(10.0)
