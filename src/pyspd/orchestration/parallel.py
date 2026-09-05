"""Deterministic, fail-closed process coordination for independent cases."""

from __future__ import annotations

import multiprocessing
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import (
    FIRST_COMPLETED,
    Executor,
    Future,
    ProcessPoolExecutor,
    wait,
)
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pyspd.data.raw import RawSymbol, RawSymbols

from .types import DailyCase, OrchestrationError, PreparedCase

T = TypeVar("T")


class ParallelExecutionError(OrchestrationError):
    """A parallel plan or one of its isolated workers failed."""


@dataclass(frozen=True, slots=True)
class CaseBoundary:
    """Minimum case metadata needed to prove an independent shard boundary."""

    case_id: str
    ordinal: int
    predecessor_independent: bool

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ParallelExecutionError("parallel case ID must not be empty")
        if self.ordinal < 0:
            raise ParallelExecutionError("parallel case ordinal must be non-negative")

    @classmethod
    def from_prepared_case(cls, prepared: PreparedCase) -> CaseBoundary:
        return cls(
            case_id=prepared.specification.case_id,
            ordinal=prepared.specification.ordinal,
            predecessor_independent=any(prepared.generation_start.values()),
        )


class GenerationStartBoundaryClassifier:
    """Classify period independence from the minimal source offer inventory."""

    def classify(
        self,
        symbols: RawSymbols,
        cases: Sequence[DailyCase],
    ) -> tuple[CaseBoundary, ...]:
        try:
            offer_parameter = _numeric(symbols["i_dateTimeOfferParameter"])
        except KeyError as error:
            raise ParallelExecutionError(
                "generation-start inventory is missing i_dateTimeOfferParameter"
            ) from error
        initial = _component(offer_parameter, "initialMW")
        solved_initial = _component(offer_parameter, "solvedInitialMW")
        try:
            primary_secondary = tuple(
                record.keys
                for record in symbols["i_dateTimePrimarySecondaryOffer"].records
            )
        except KeyError:
            primary_secondary = ()
        offer_identities = frozenset(key[:3] for key in offer_parameter)
        offers_by_period: dict[tuple[str, str], list[tuple[str, str, str]]] = (
            defaultdict(list)
        )
        for raw_identity in offer_identities:
            case_id, date_time, offer = raw_identity
            identity = (case_id, date_time, offer)
            offers_by_period[(case_id, date_time)].append(identity)
        all_initial_zero: dict[tuple[str, str], bool] = {}
        for (case_id, _date_time, offer), value in initial.items():
            key = (case_id, offer)
            all_initial_zero[key] = all_initial_zero.get(key, True) and value == 0.0
        secondaries_by_primary: dict[tuple[str, str, str], list[str]] = defaultdict(
            list
        )
        for case_id, date_time, primary, secondary in primary_secondary:
            secondaries_by_primary[(case_id, date_time, primary)].append(secondary)

        boundaries: list[CaseBoundary] = []
        for case in cases:
            period = (case.case_id, case.date_time)
            is_rtd = case.study_mode in {101, 201}
            use_initial = is_rtd or case.study_mode == 111
            nonzero_start = False
            for identity in offers_by_period[period]:
                offer = identity[2]
                value = (
                    initial.get(identity, 0.0)
                    if use_initial
                    else solved_initial.get(identity, 0.0)
                )
                if not is_rtd and all_initial_zero.get((case.case_id, offer), False):
                    value = solved_initial.get(identity, 0.0)
                value += sum(
                    initial.get((case.case_id, case.date_time, secondary), 0.0)
                    for secondary in secondaries_by_primary[identity]
                )
                if value != 0.0:
                    nonzero_start = True
                    break
            boundaries.append(
                CaseBoundary(case.case_id, case.ordinal, nonzero_start)
            )
        return tuple(boundaries)


def _numeric(symbol: RawSymbol) -> dict[tuple[str, ...], float]:
    return {
        record.keys: float(value.number)
        for record in symbol.records
        if (value := record.values.get("value")) is not None
        and value.number is not None
    }


def _component(
    values: dict[tuple[str, ...], float], component: str
) -> dict[tuple[str, ...], float]:
    wanted = component.casefold()
    return {
        key[:-1]: value
        for key, value in values.items()
        if key[-1].casefold() == wanted
    }


@dataclass(frozen=True, slots=True)
class CaseShard:
    """One contiguous half-open range in canonical source order."""

    index: int
    start_ordinal: int
    stop_ordinal: int
    case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if self.index < 0 or self.start_ordinal < 0:
            raise ParallelExecutionError("parallel shard indices must be non-negative")
        if self.stop_ordinal <= self.start_ordinal:
            raise ParallelExecutionError("parallel shard range must not be empty")
        if len(self.case_ids) != self.case_count:
            raise ParallelExecutionError("parallel shard range and case IDs disagree")

    @property
    def case_count(self) -> int:
        return self.stop_ordinal - self.start_ordinal


@dataclass(frozen=True, slots=True)
class CaseShardPlan:
    """Auditable case-job plan executed by a bounded process pool."""

    requested_workers: int
    total_case_count: int
    shards: tuple[CaseShard, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "shards", tuple(self.shards))
        if (
            isinstance(self.requested_workers, bool)
            or self.requested_workers <= 0
            or self.total_case_count <= 0
        ):
            raise ParallelExecutionError("parallel plan counts must be positive")
        if not self.shards:
            raise ParallelExecutionError("parallel plan must contain jobs")
        if tuple(shard.index for shard in self.shards) != tuple(
            range(len(self.shards))
        ):
            raise ParallelExecutionError("parallel plan shard indexes are not canonical")
        expected_start = 0
        for shard in self.shards:
            if shard.start_ordinal != expected_start:
                raise ParallelExecutionError("parallel plan shard ranges are not contiguous")
            expected_start = shard.stop_ordinal
        if expected_start != self.total_case_count:
            raise ParallelExecutionError("parallel plan does not cover its case count")

    @property
    def worker_count(self) -> int:
        return min(self.requested_workers, len(self.shards))

    @property
    def job_count(self) -> int:
        return len(self.shards)


class ContiguousCaseShardPlanner:
    """Split canonical cases evenly without crossing an unproved boundary."""

    def plan(
        self, boundaries: Sequence[CaseBoundary], *, workers: int
    ) -> CaseShardPlan:
        if isinstance(workers, bool) or workers <= 0:
            raise ParallelExecutionError("parallel workers must be a positive integer")
        items = tuple(boundaries)
        if not items:
            raise ParallelExecutionError("parallel case inventory must not be empty")
        if tuple(item.ordinal for item in items) != tuple(range(len(items))):
            raise ParallelExecutionError(
                "parallel case inventory is not in canonical ordinal order"
            )

        worker_count = min(workers, len(items))
        base, remainder = divmod(len(items), worker_count)
        shards: list[CaseShard] = []
        start = 0
        for index in range(worker_count):
            count = base + (1 if index < remainder else 0)
            stop = start + count
            boundary = items[start]
            if start and not boundary.predecessor_independent:
                raise ParallelExecutionError(
                    f"case {boundary.case_id!r} at shard {index} requires predecessor "
                    "generation state"
                )
            shards.append(
                CaseShard(
                    index=index,
                    start_ordinal=start,
                    stop_ordinal=stop,
                    case_ids=tuple(item.case_id for item in items[start:stop]),
                )
            )
            start = stop
        return CaseShardPlan(workers, len(items), tuple(shards))


class DynamicCaseJobPlanner:
    """Create small ordered jobs for dynamic assignment to idle workers."""

    def plan(
        self,
        boundaries: Sequence[CaseBoundary],
        *,
        workers: int,
        cases_per_job: int = 1,
    ) -> CaseShardPlan:
        if isinstance(workers, bool) or workers <= 0:
            raise ParallelExecutionError("parallel workers must be a positive integer")
        if isinstance(cases_per_job, bool) or cases_per_job <= 0:
            raise ParallelExecutionError("parallel cases per job must be positive")
        items = tuple(boundaries)
        if not items:
            raise ParallelExecutionError("parallel case inventory must not be empty")
        if tuple(item.ordinal for item in items) != tuple(range(len(items))):
            raise ParallelExecutionError(
                "parallel case inventory is not in canonical ordinal order"
            )

        jobs: list[CaseShard] = []
        for start in range(0, len(items), cases_per_job):
            stop = min(start + cases_per_job, len(items))
            boundary = items[start]
            if start and not boundary.predecessor_independent:
                raise ParallelExecutionError(
                    f"case {boundary.case_id!r} at job {len(jobs)} requires "
                    "predecessor generation state"
                )
            jobs.append(
                CaseShard(
                    index=len(jobs),
                    start_ordinal=start,
                    stop_ordinal=stop,
                    case_ids=tuple(item.case_id for item in items[start:stop]),
                )
            )
        return CaseShardPlan(workers, len(items), tuple(jobs))


class _ExecutorFactory(Protocol):
    def __call__(self, max_workers: int) -> Executor: ...


def _spawn_process_pool(max_workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=multiprocessing.get_context("spawn"),
    )


class ProcessShardCoordinator:
    """Assign jobs to idle processes and restore deterministic source order."""

    def __init__(self, *, executor_factory: _ExecutorFactory | None = None) -> None:
        self._executor_factory = executor_factory or _spawn_process_pool

    def run(
        self,
        plan: CaseShardPlan,
        worker: Callable[[CaseShard], T],
    ) -> tuple[T, ...]:
        executor = self._executor_factory(plan.worker_count)
        futures: dict[Future[T], CaseShard] = {}
        pending_shards = iter(plan.shards)

        def submit_next() -> bool:
            try:
                shard = next(pending_shards)
            except StopIteration:
                return False
            try:
                future = executor.submit(worker, shard)
            except Exception as error:
                raise ParallelExecutionError(
                    f"could not submit parallel shard {shard.index}"
                ) from error
            futures[future] = shard
            return True

        try:
            for _ in range(plan.worker_count):
                submit_next()

            ordered: list[T | None] = [None] * plan.job_count
            completed: set[int] = set()
            while futures:
                done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    shard = futures.pop(future)
                    try:
                        ordered[shard.index] = future.result()
                    except Exception as error:
                        for pending in futures:
                            pending.cancel()
                        raise ParallelExecutionError(
                            f"parallel shard {shard.index} beginning with "
                            f"{shard.case_ids[0]!r} failed: {error}"
                        ) from error
                    completed.add(shard.index)
                    submit_next()
            if len(completed) != plan.job_count:
                raise ParallelExecutionError("parallel run returned incomplete shards")
            return tuple(ordered[index] for index in range(plan.job_count))  # type: ignore[misc]
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
