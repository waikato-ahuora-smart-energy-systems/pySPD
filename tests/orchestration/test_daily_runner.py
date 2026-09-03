from __future__ import annotations

from dataclasses import replace

import pytest

from pyspd.orchestration import (
    CaseRunStatus,
    DailyRunConfiguration,
    DailyRunner,
    DailyRunState,
    OrchestrationError,
    RunEventKind,
)
from tests.orchestration.conftest import (
    SequenceExecutor,
    make_daily_case,
    make_observation,
    make_prepared,
)


class FailingExecutor:
    def solve(self, prepared):
        del prepared
        raise RuntimeError("synthetic solver failure")


def configuration() -> DailyRunConfiguration:
    return DailyRunConfiguration("vspd-v5.0.6-reserve", "0" * 64, 3)


def test_shortfall_transfer_resolves_and_records_each_transition() -> None:
    executor = SequenceExecutor(
        [make_observation(shortfall=1.0), make_observation(shortfall=0.0)]
    )
    result = DailyRunner(executor).run(configuration(), (make_prepared(),))
    case = result.cases[0]
    n1 = ("C1", "01-JAN-2024 00:00", "N1")
    n2 = ("C1", "01-JAN-2024 00:00", "N2")
    assert result.state is DailyRunState.COMPLETE
    assert case.solve_count == 2
    assert case.transfers[(n1, n2)] == 1.2
    assert case.final_required_load[n1] == 8.8
    assert case.final_required_load[n2] == 21.2
    assert RunEventKind.SHORTFALL_TRANSFERRED in {event.kind for event in case.events}


def test_disconnected_bus_state_persists_across_shortfall_resolve() -> None:
    ca, dt = "C1", "01-JAN-2024 00:00"
    b1, b2 = (ca, dt, "B1"), (ca, dt, "B2")
    first = replace(
        make_observation(shortfall=1.0),
        bus_generation={b1: 0.0, b2: 20.0},
        bus_load={b1: 0.3, b2: 20.0},
        bus_electrical_island={b1: 0.0, b2: 1.0},
    )
    second = replace(
        make_observation(shortfall=0.0),
        bus_generation={b1: 0.3, b2: 20.0},
        bus_load={b1: 0.3, b2: 20.0},
        bus_electrical_island={b1: 0.0, b2: 1.0},
    )

    result = DailyRunner(SequenceExecutor([first, second])).run(
        configuration(), (make_prepared(),)
    )

    prices = result.cases[0].prices
    assert prices is not None
    assert prices.repaired_bus[b1] == 0.0
    assert b1 in prices.disconnected_buses


def test_bounded_loop_exposes_degraded_result_instead_of_hanging() -> None:
    observation = make_observation(shortfall=1.0)
    executor = SequenceExecutor([observation, observation, observation])
    result = DailyRunner(executor).run(configuration(), (make_prepared(),))
    case = result.cases[0]
    assert case.status is CaseRunStatus.DEGRADED
    assert case.solve_count == 3
    assert len(case.transfers) == 1
    assert len(executor.calls) == 3
    assert RunEventKind.LOOP_LIMIT_REACHED in {event.kind for event in case.events}
    assert not any(
        event.kind is RunEventKind.SOLVE_STARTED and event.solve_loop == 4
        for event in case.events
    )


def test_ineligible_shortfall_disables_scaling_once_then_accepts() -> None:
    prepared = replace(
        make_prepared(),
        load_bad_nodes=frozenset(),
        potential_inconsistency_nodes=frozenset(),
    )
    executor = SequenceExecutor(
        [make_observation(shortfall=1.0), make_observation(shortfall=1.0)]
    )
    result = DailyRunner(executor).run(configuration(), (prepared,))
    case = result.cases[0]
    node = ("C1", "01-JAN-2024 00:00", "N1")
    assert case.solve_count == 2
    assert executor.calls[1].scaling_disabled_nodes == frozenset({node})
    assert (
        sum(
            event.kind is RunEventKind.SHORTFALL_SCALING_DISABLED
            for event in case.events
        )
        == 1
    )


def test_daily_mode_does_not_resolve_for_scaling_disable_only() -> None:
    prepared = replace(
        make_prepared(),
        load_bad_nodes=frozenset(),
        potential_inconsistency_nodes=frozenset(),
        rtd_load_reconstruction_enabled=False,
    )
    executor = SequenceExecutor([make_observation(shortfall=1.0)])

    result = DailyRunner(executor).run(configuration(), (prepared,))

    assert result.cases[0].solve_count == 1
    assert len(executor.calls) == 1
    assert RunEventKind.SHORTFALL_SCALING_DISABLED not in {
        event.kind for event in result.cases[0].events
    }


def test_override_audit_is_visible_before_solve() -> None:
    prepared = replace(
        make_prepared(),
        override_entry_count=3,
        override_input_sha256="1" * 64,
        override_output_sha256="2" * 64,
    )
    result = DailyRunner(SequenceExecutor([make_observation()])).run(
        configuration(), (prepared,)
    )
    event = next(
        item
        for item in result.cases[0].events
        if item.kind is RunEventKind.OVERRIDES_APPLIED
    )
    assert event.details == {"entry_count": 3, "symbols_changed": True}


def test_unresolved_invalid_prices_make_case_quality_explicitly_degraded() -> None:
    observation = make_observation(raw_prices=(0.0, 0.0), sos=True)
    observation = replace(
        observation,
        connected_bus_flow=dict.fromkeys(observation.connected_bus_flow, 0.0),
    )
    result = DailyRunner(SequenceExecutor([observation])).run(
        configuration(), (make_prepared(),)
    )
    case = result.cases[0]
    assert case.status is CaseRunStatus.DEGRADED
    assert case.prices is not None
    assert case.prices.invalid_buses


def test_prior_accepted_generation_initializes_zero_start_next_case() -> None:
    first = make_prepared(make_daily_case())
    second = make_prepared(make_daily_case("C2", "01-JAN-2024 00:05", ordinal=1))
    executor = SequenceExecutor(
        [make_observation(generation=42.0), make_observation(second.specification)]
    )
    DailyRunner(executor).run(configuration(), (first, second))
    assert executor.calls[1].generation_start["G1"] == 42.0


def test_interrupted_run_resumes_exact_prefix_and_rejects_environment_mix() -> None:
    first = make_prepared(make_daily_case())
    second = make_prepared(make_daily_case("C2", "01-JAN-2024 00:05", ordinal=1))
    executor = SequenceExecutor(
        [make_observation(), make_observation(second.specification)]
    )
    interrupted = DailyRunner(executor).run(
        configuration(), (first, second), stop_after=1
    )
    assert interrupted.state is DailyRunState.INTERRUPTED
    assert interrupted.checkpoint is not None
    resumed = DailyRunner(executor).run(
        configuration(), (first, second), resume=interrupted.checkpoint
    )
    assert resumed.state is DailyRunState.COMPLETE
    assert len(resumed.cases) == 2
    changed = DailyRunConfiguration(
        "vspd-v5.0.6-reserve",
        "0" * 64,
        3,
        environment_fingerprint="different",
    )
    try:
        DailyRunner(executor).run(
            changed, (first, second), resume=interrupted.checkpoint
        )
    except OrchestrationError as error:
        assert "configuration/environment mismatch" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unsafe resume was accepted")


def test_solver_failure_retains_the_exact_case_identity() -> None:
    prepared = make_prepared(make_daily_case("case-failed"))

    with pytest.raises(
        OrchestrationError,
        match="case case-failed solve failed: synthetic solver failure",
    ):
        DailyRunner(FailingExecutor()).run(configuration(), (prepared,))
