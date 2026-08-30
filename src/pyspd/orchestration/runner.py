"""Inspectable and resumable Gate 8 daily run state machine."""

from __future__ import annotations

from dataclasses import replace

from .pricing import MarketPricePostProcessor, PublishedPriceAggregator
from .solver import CaseExecutor, ShortfallLoop
from .types import (
    CaseRunResult,
    CaseRunStatus,
    DailyRunCheckpoint,
    DailyRunConfiguration,
    DailyRunResult,
    DailyRunState,
    OrchestrationError,
    PreparedCase,
    RunEvent,
    RunEventKind,
)


class DailyRunner:
    """Run selected cases in order without hiding re-solves or degraded states."""

    def __init__(
        self,
        executor: CaseExecutor,
        *,
        postprocessor: MarketPricePostProcessor | None = None,
        publisher: PublishedPriceAggregator | None = None,
    ) -> None:
        self.executor = executor
        self.postprocessor = postprocessor or MarketPricePostProcessor()
        self.publisher = publisher or PublishedPriceAggregator()

    def run(
        self,
        configuration: DailyRunConfiguration,
        cases: tuple[PreparedCase, ...],
        *,
        resume: DailyRunCheckpoint | None = None,
        stop_after: int | None = None,
    ) -> DailyRunResult:
        self._validate_inputs(configuration, cases)
        configuration_hash = configuration.logical_sha256
        if resume is None:
            completed: list[CaseRunResult] = []
            previous_generation: dict[str, float] = {}
            next_ordinal = 0
            events: list[RunEvent] = []
            sequence = 0
        else:
            if resume.configuration_sha256 != configuration_hash:
                raise OrchestrationError(
                    "resume checkpoint configuration/environment mismatch"
                )
            if tuple(item.specification.case_id for item in resume.completed) != tuple(
                item.specification.case_id for item in cases[: resume.next_case_ordinal]
            ):
                raise OrchestrationError("resume checkpoint case prefix mismatch")
            completed = list(resume.completed)
            previous_generation = dict(resume.previous_generation)
            next_ordinal = resume.next_case_ordinal
            events = [event for result in completed for event in result.events]
            sequence = resume.event_sequence
            events.append(
                RunEvent(
                    sequence,
                    RunEventKind.RESUMED,
                    None,
                    details={"next_case": next_ordinal},
                )
            )
            sequence += 1
        for processed_this_call, prepared in enumerate(cases[next_ordinal:], start=1):
            case_events: list[RunEvent] = []
            sink = _EventSink(
                events, case_events, sequence, prepared.specification.case_id
            )
            emit = sink.emit

            emit(RunEventKind.CASE_SELECTED)
            generation_start = dict(prepared.generation_start)
            used_fallback = False
            if not any(generation_start.values()) and previous_generation:
                generation_start.update(previous_generation)
                prepared = replace(prepared, generation_start=generation_start)
                used_fallback = True
            emit(
                RunEventKind.INITIALIZED,
                details={"prior_period_fallback": used_fallback},
            )
            emit(
                RunEventKind.OVERRIDES_APPLIED,
                details={
                    "entry_count": prepared.override_entry_count,
                    "symbols_changed": (
                        prepared.override_input_sha256
                        != prepared.override_output_sha256
                    ),
                },
            )
            emit(RunEventKind.SOLVE_STARTED, solve_loop=1)
            try:
                loop = ShortfallLoop(
                    self.executor, tolerance=configuration.residual_tolerance
                ).run(prepared, maximum_loops=configuration.maximum_solve_loops)
            except Exception as error:
                raise OrchestrationError(
                    f"case {prepared.specification.case_id} solve failed: {error}"
                ) from error
            for transition in loop.transitions:
                if transition.transfers or transition.untransferred:
                    emit(
                        RunEventKind.SHORTFALL_TRANSFERRED,
                        solve_loop=transition.solve_loop,
                        details={
                            "transfer_count": len(transition.transfers),
                            "untransferred_count": len(transition.untransferred),
                        },
                    )
                if transition.scaling_disabled:
                    emit(
                        RunEventKind.SHORTFALL_SCALING_DISABLED,
                        solve_loop=transition.solve_loop,
                        details={"node_count": len(transition.scaling_disabled)},
                    )
                emit(
                    RunEventKind.SOLVE_STARTED,
                    solve_loop=transition.solve_loop + 1,
                )
            emit(
                RunEventKind.SOLVE_ACCEPTED,
                solve_loop=loop.solve_count,
                details={"objective": loop.accepted.objective},
            )
            prices = self.postprocessor.process(
                loop.accepted,
                price_transfer_enabled=prepared.price_transfer_enabled,
            )
            emit(
                RunEventKind.PRICES_REPAIRED,
                details={
                    "invalid_bus_count": len(prices.invalid_buses),
                    "dead_node_count": len(prices.dead_nodes),
                },
            )
            degraded = bool(
                loop.limit_reached
                or loop.accepted.degraded_reasons
                or prices.invalid_buses
            )
            if loop.limit_reached:
                emit(
                    RunEventKind.LOOP_LIMIT_REACHED,
                    solve_loop=loop.solve_count,
                )
            status = CaseRunStatus.DEGRADED if degraded else CaseRunStatus.COMPLETE
            emit(RunEventKind.CASE_COMPLETE, details={"status": status.value})
            result = CaseRunResult(
                prepared.specification,
                status,
                loop.solve_count,
                loop.accepted,
                prices,
                tuple(case_events),
                loop.prepared.required_load,
                loop.transfers,
                loop.untransferred,
            )
            completed.append(result)
            previous_generation = dict(loop.accepted.generation)
            next_ordinal += 1
            sequence = sink.sequence
            if (
                stop_after is not None
                and processed_this_call >= stop_after
                and next_ordinal < len(cases)
            ):
                checkpoint = DailyRunCheckpoint(
                    configuration_hash,
                    next_ordinal,
                    tuple(completed),
                    previous_generation,
                    sequence + 1,
                )
                checkpoint_event = RunEvent(
                    sequence,
                    RunEventKind.CHECKPOINT_WRITTEN,
                    None,
                    details={"next_case": next_ordinal},
                )
                events.append(checkpoint_event)
                return DailyRunResult(
                    DailyRunState.INTERRUPTED,
                    configuration_hash,
                    tuple(completed),
                    None,
                    tuple(events),
                    checkpoint,
                )
        published = self.publisher.aggregate(
            tuple(completed), decimals=configuration.price_rounding_decimals
        )
        events.append(
            RunEvent(
                sequence,
                RunEventKind.PRICES_PUBLISHED,
                None,
                details={
                    "energy_count": len(published.energy),
                    "reserve_count": len(published.reserve),
                },
            )
        )
        state = (
            DailyRunState.FAILED
            if any(item.status is CaseRunStatus.FAILED for item in completed)
            else DailyRunState.COMPLETE
        )
        return DailyRunResult(
            state,
            configuration_hash,
            tuple(completed),
            published,
            tuple(events),
        )

    @staticmethod
    def _validate_inputs(
        configuration: DailyRunConfiguration, cases: tuple[PreparedCase, ...]
    ) -> None:
        identities: set[str] = set()
        for ordinal, prepared in enumerate(cases):
            selected = prepared.specification
            if selected.ordinal != ordinal:
                raise OrchestrationError("prepared cases are not in canonical order")
            if selected.case_id in identities:
                raise OrchestrationError("duplicate selected case")
            identities.add(selected.case_id)
            if selected.source_sha256 != configuration.source_sha256:
                raise OrchestrationError("case source does not match run configuration")


class _EventSink:
    def __init__(
        self,
        events: list[RunEvent],
        case_events: list[RunEvent],
        sequence: int,
        case_id: str,
    ) -> None:
        self.events = events
        self.case_events = case_events
        self.sequence = sequence
        self.case_id = case_id

    def emit(
        self,
        kind: RunEventKind,
        *,
        solve_loop: int | None = None,
        details: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        event = RunEvent(
            self.sequence,
            kind,
            self.case_id,
            solve_loop,
            details or {},
        )
        self.sequence += 1
        self.case_events.append(event)
        self.events.append(event)
