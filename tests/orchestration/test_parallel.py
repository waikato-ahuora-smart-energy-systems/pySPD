from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass

import pytest

from pyspd.data import RawRecord, RawSymbol, RawSymbols, ScalarValue, SymbolType
from pyspd.orchestration import (
    CaseBoundary,
    CaseShard,
    CaseShardPlan,
    ContiguousCaseShardPlanner,
    DynamicCaseJobPlanner,
    GenerationStartBoundaryClassifier,
    ParallelExecutionError,
    ProcessShardCoordinator,
    ScheduleType,
)
from tests.orchestration.conftest import make_daily_case


def _boundaries(
    count: int, *, dependent_ordinals: frozenset[int] = frozenset()
) -> tuple[CaseBoundary, ...]:
    return tuple(
        CaseBoundary(
            case_id=f"CASE-{ordinal}",
            ordinal=ordinal,
            predecessor_independent=ordinal not in dependent_ordinals,
        )
        for ordinal in range(count)
    )


def _parameter_symbol(
    name: str,
    domains: tuple[str, ...],
    records: tuple[tuple[tuple[str, ...], float], ...],
) -> RawSymbol:
    return RawSymbol(
        name,
        SymbolType.PARAMETER,
        len(domains),
        domains,
        name,
        tuple(() for _ in domains),
        tuple(
            RawRecord(keys, {"value": ScalarValue.finite(value)})
            for keys, value in records
        ),
    )


def test_generation_start_classifier_matches_daily_mode_offer_rules() -> None:
    cases = (
        make_daily_case("RTD-NONZERO", "01-JAN-2024 00:00", ordinal=0),
        make_daily_case("RTD-ZERO", "01-JAN-2024 00:05", ordinal=1),
        make_daily_case(
            "PRSS-SOLVED", "01-JAN-2024 00:10", ordinal=2,
            schedule_type=ScheduleType.PRSS,
        ),
        make_daily_case(
            "PRSS-ZERO", "01-JAN-2024 00:15", ordinal=3,
            schedule_type=ScheduleType.PRSS,
        ),
    )
    run_mode = _parameter_symbol(
        "i_runMode",
        ("ca", "runParameter"),
        tuple(
            ((case.case_id, "studyMode"), float(case.study_mode)) for case in cases
        ),
    )
    offer_records: list[tuple[tuple[str, ...], float]] = []
    inputs = {
        "RTD-NONZERO": (12.0, 0.0),
        "RTD-ZERO": (0.0, 15.0),
        "PRSS-SOLVED": (0.0, 18.0),
        "PRSS-ZERO": (5.0, 0.0),
    }
    for case in cases:
        initial, solved = inputs[case.case_id]
        offer_records.extend(
            (
                ((case.case_id, case.date_time, "O1", "initialMW"), initial),
                ((case.case_id, case.date_time, "O1", "solvedInitialMW"), solved),
            )
        )
    offers = _parameter_symbol(
        "i_dateTimeOfferParameter",
        ("ca", "dt", "o", "offerParameter"),
        tuple(offer_records),
    )
    primary_secondary = RawSymbol(
        "i_dateTimePrimarySecondaryOffer",
        SymbolType.SET,
        4,
        ("ca", "dt", "o", "o1"),
        "primary secondary",
        ((), (), (), ()),
        (),
    )
    symbols = RawSymbols("synthetic.gdx", "0" * 64, (run_mode, offers, primary_secondary))

    boundaries = GenerationStartBoundaryClassifier().classify(symbols, cases)

    assert [boundary.predecessor_independent for boundary in boundaries] == [
        True,
        False,
        True,
        False,
    ]


def test_contiguous_planner_balances_and_preserves_canonical_order() -> None:
    plan = ContiguousCaseShardPlanner().plan(_boundaries(10), workers=3)

    assert plan.requested_workers == 3
    assert plan.worker_count == 3
    assert [shard.start_ordinal for shard in plan.shards] == [0, 4, 7]
    assert [shard.case_count for shard in plan.shards] == [4, 3, 3]
    assert tuple(
        case_id for shard in plan.shards for case_id in shard.case_ids
    ) == tuple(f"CASE-{ordinal}" for ordinal in range(10))


def test_contiguous_planner_caps_workers_at_case_count() -> None:
    plan = ContiguousCaseShardPlanner().plan(_boundaries(2), workers=10)

    assert plan.requested_workers == 10
    assert plan.worker_count == 2
    assert [shard.case_count for shard in plan.shards] == [1, 1]


def test_dynamic_planner_creates_more_jobs_than_workers_in_canonical_order() -> None:
    plan = DynamicCaseJobPlanner().plan(_boundaries(10), workers=3, cases_per_job=2)

    assert plan.requested_workers == 3
    assert plan.worker_count == 3
    assert len(plan.shards) == 5
    assert [shard.case_count for shard in plan.shards] == [2, 2, 2, 2, 2]
    assert tuple(
        case_id for shard in plan.shards for case_id in shard.case_ids
    ) == tuple(f"CASE-{ordinal}" for ordinal in range(10))


def test_dynamic_planner_keeps_final_partial_job() -> None:
    plan = DynamicCaseJobPlanner().plan(_boundaries(5), workers=10, cases_per_job=2)

    assert plan.worker_count == 3
    assert [shard.case_count for shard in plan.shards] == [2, 2, 1]


def test_dynamic_planner_preserves_duplicate_labels_by_distinct_ordinal() -> None:
    boundaries = (
        CaseBoundary("DUPLICATE", 0, True),
        CaseBoundary("DUPLICATE", 1, True),
        CaseBoundary("UNIQUE", 2, True),
    )

    plan = DynamicCaseJobPlanner().plan(
        boundaries, workers=2, cases_per_job=2
    )

    assert [(shard.start_ordinal, shard.case_ids) for shard in plan.shards] == [
        (0, ("DUPLICATE", "DUPLICATE")),
        (2, ("UNIQUE",)),
    ]


def test_dynamic_planner_fails_closed_at_each_job_boundary() -> None:
    with pytest.raises(ParallelExecutionError, match="CASE-2.*predecessor"):
        DynamicCaseJobPlanner().plan(
            _boundaries(5, dependent_ordinals=frozenset({2})),
            workers=2,
            cases_per_job=2,
        )


@pytest.mark.parametrize("cases_per_job", [0, -1, True])
def test_dynamic_planner_rejects_invalid_job_size(cases_per_job: int) -> None:
    with pytest.raises(ParallelExecutionError, match="cases per job"):
        DynamicCaseJobPlanner().plan(
            _boundaries(5), workers=2, cases_per_job=cases_per_job
        )


def test_contiguous_planner_fails_closed_at_predecessor_dependent_boundary() -> None:
    with pytest.raises(ParallelExecutionError, match="CASE-4.*predecessor"):
        ContiguousCaseShardPlanner().plan(
            _boundaries(10, dependent_ordinals=frozenset({4})), workers=3
        )


def test_contiguous_planner_rejects_noncanonical_boundary_inventory() -> None:
    invalid = (
        CaseBoundary("CASE-0", 0, True),
        CaseBoundary("CASE-2", 2, True),
    )

    with pytest.raises(ParallelExecutionError, match="canonical"):
        ContiguousCaseShardPlanner().plan(invalid, workers=2)


def test_case_shard_plan_rejects_noncanonical_manual_construction() -> None:
    shards = (
        CaseShard(0, 0, 2, ("CASE-0", "CASE-1")),
        CaseShard(2, 2, 4, ("CASE-2", "CASE-3")),
    )

    with pytest.raises(ParallelExecutionError, match="shard indexes"):
        CaseShardPlan(2, 4, shards)


@dataclass
class _RecordingExecutor:
    max_workers: int
    reverse_completion: bool = False
    failed_index: int | None = None

    def __post_init__(self) -> None:
        self.submitted: list[int] = []

    def submit(self, worker, shard):
        self.submitted.append(shard.index)
        future: Future[str] = Future()
        if shard.index == self.failed_index:
            future.set_exception(RuntimeError("synthetic worker failure"))
        else:
            future.set_result(worker(shard))
        return future

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        assert wait
        assert cancel_futures


def _identify_shard(shard) -> str:
    return f"{shard.index}:{shard.start_ordinal}:{shard.stop_ordinal}"


def test_process_coordinator_returns_results_in_shard_order() -> None:
    executors: list[_RecordingExecutor] = []

    def factory(max_workers: int) -> _RecordingExecutor:
        executor = _RecordingExecutor(max_workers)
        executors.append(executor)
        return executor

    plan = ContiguousCaseShardPlanner().plan(_boundaries(7), workers=3)
    results = ProcessShardCoordinator(executor_factory=factory).run(
        plan, _identify_shard
    )

    assert results == ("0:0:3", "1:3:5", "2:5:7")
    assert executors[0].max_workers == 3
    assert executors[0].submitted == [0, 1, 2]


def test_process_coordinator_schedules_all_dynamic_jobs_with_bounded_workers() -> None:
    executors: list[_RecordingExecutor] = []

    def factory(max_workers: int) -> _RecordingExecutor:
        executor = _RecordingExecutor(max_workers)
        executors.append(executor)
        return executor

    plan = DynamicCaseJobPlanner().plan(_boundaries(7), workers=3, cases_per_job=1)
    results = ProcessShardCoordinator(executor_factory=factory).run(
        plan, _identify_shard
    )

    assert results == tuple(f"{index}:{index}:{index + 1}" for index in range(7))
    assert executors[0].max_workers == 3
    assert executors[0].submitted == list(range(7))


def test_process_coordinator_does_not_queue_more_jobs_than_workers() -> None:
    submitted: list[int] = []
    counts = {"outstanding": 0, "peak": 0}

    class CountingFuture(Future[str]):
        def result(self, timeout=None):
            counts["outstanding"] -= 1
            return super().result(timeout)

    class ControlledExecutor:
        def submit(self, worker, shard):
            counts["outstanding"] += 1
            counts["peak"] = max(counts["peak"], counts["outstanding"])
            assert counts["outstanding"] <= 2
            submitted.append(shard.index)
            future = CountingFuture()
            future.set_result(worker(shard))
            return future

        def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
            assert wait
            assert cancel_futures

    plan = DynamicCaseJobPlanner().plan(_boundaries(7), workers=2, cases_per_job=1)

    ProcessShardCoordinator(executor_factory=lambda _: ControlledExecutor()).run(
        plan, _identify_shard
    )

    assert submitted == list(range(7))
    assert counts == {"outstanding": 0, "peak": 2}


def test_process_coordinator_identifies_failed_shard() -> None:
    plan = ContiguousCaseShardPlanner().plan(_boundaries(4), workers=2)
    executor = _RecordingExecutor(2, failed_index=1)

    with pytest.raises(ParallelExecutionError, match="shard 1.*CASE-2"):
        ProcessShardCoordinator(executor_factory=lambda _: executor).run(
            plan, _identify_shard
        )
