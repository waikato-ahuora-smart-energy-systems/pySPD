from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from pyspd.application import ParallelCaseResultCodec, ParallelDailyResultAssembler
from pyspd.orchestration import (
    DailyRunConfiguration,
    DailyRunner,
    RunEventKind,
)
from tests.orchestration.conftest import (
    SequenceExecutor,
    make_daily_case,
    make_observation,
    make_prepared,
)


def _configuration() -> DailyRunConfiguration:
    return DailyRunConfiguration("vspd-v5.0.6-reserve", "0" * 64)


def test_parallel_case_result_codec_strips_live_solver_payload_and_round_trips() -> None:
    opaque_solver_payload = object()
    observation = replace(make_observation(), solve_payload=opaque_solver_payload)
    result = DailyRunner(SequenceExecutor([observation])).run(
        _configuration(), (make_prepared(),)
    ).cases[0]

    encoded = ParallelCaseResultCodec().encode(result)
    decoded = ParallelCaseResultCodec().decode(encoded)

    assert decoded.specification == result.specification
    assert decoded.status == result.status
    assert decoded.accepted is not None
    assert decoded.accepted.solve_payload is None
    assert dict(decoded.accepted.generation) == dict(result.accepted.generation)
    assert decoded.prices == result.prices
    assert decoded.events == result.events


def test_parallel_daily_assembler_restores_serial_order_and_event_sequence() -> None:
    first = make_prepared(make_daily_case("C1", ordinal=0))
    second = make_prepared(
        make_daily_case("C2", "01-JAN-2024 00:05", "TP2", ordinal=1)
    )
    first_result = DailyRunner(SequenceExecutor([make_observation(first.specification)])).run(
        _configuration(), (first,)
    ).cases[0]
    second_local = replace(second, specification=replace(second.specification, ordinal=0))
    second_result = DailyRunner(
        SequenceExecutor([make_observation(second_local.specification)])
    ).run(_configuration(), (second_local,)).cases[0]
    second_result = replace(second_result, specification=second.specification)
    codec = ParallelCaseResultCodec()

    assembled = ParallelDailyResultAssembler().assemble(
        _configuration(),
        (codec.encode(first_result), codec.encode(second_result)),
    )

    assert [case.specification.case_id for case in assembled.cases] == ["C1", "C2"]
    assert [event.sequence for event in assembled.events] == list(
        range(len(assembled.events))
    )
    assert assembled.events[-1].kind is RunEventKind.PRICES_PUBLISHED
    assert assembled.published is not None
    assert set(assembled.published.total_seconds) == {"TP1", "TP2"}


def test_parallel_application_evidence_is_identity_strict_and_materially_faster() -> None:
    evidence = json.loads(
        Path("private/docs/gate-12/parallel-application-integration-20190218.json").read_text()
    )

    assert evidence["decision"] == "qualified-production-application-path"
    assert evidence["performance"]["wall_time_reduction_percent"] > 30.0
    assert evidence["report_parity"] == {
        "table_count": 12,
        "row_count": 70470,
        "identity_sets_match": True,
        "identity_order_matches": True,
        "published_price_bytes_match": True,
        "numeric_difference_count": 8,
        "maximum_absolute_difference": 5e-14,
        "maximum_difference_table": "island",
        "non_numeric_difference_count": 0,
        "passed_at_tolerance": 1e-12,
    }
    planning = evidence["full_day_boundary_benchmark"]
    assert planning["selected_case_count"] == planning["predecessor_independent_count"]
    assert planning["generation_start_classification_seconds"] < 0.1
