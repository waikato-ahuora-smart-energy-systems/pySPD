"""Probity tests for durable within-date PySPD replay checkpoints."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from pyspd.application import PORTABLE_SOLVER_PROFILE, ApplicationConfiguration
from pyspd.orchestration import DailyCaseRunner, DailyRunConfiguration
from pyspd.reporting import ArtifactProvenance, daily_report_registry
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from tests.orchestration.conftest import (
    SequenceExecutor,
    make_daily_case,
    make_observation,
    make_prepared,
)
from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.execution_provenance import python_execution_sha256
from tools.gate12.incremental_replay import IncrementalReplayWorkItem
from tools.gate12.pyspd_surfaces import (
    PARTIAL_E2E_SURFACES,
    CanonicalPartialCaseSurfaces,
)
from tools.gate12.streaming_pyspd import (
    PyspdReplayProgress,
    PyspdReplayProgressStore,
    StreamingPyspdReplayRunner,
)

EXECUTION_SHA256 = "e" * 64


def _configuration(tmp_path) -> ApplicationConfiguration:
    source = tmp_path / "input.gdx"
    source.write_bytes(b"immutable-gdx")
    system = tmp_path / "gams"
    system.mkdir()
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    return ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=source,
        output_directory=tmp_path / "reports",
        source_sha256=source_sha256,
        gams_system_directory=system,
        solver_profile=PORTABLE_SOLVER_PROFILE,
        case_ids=("warmup", "affected"),
    )


def _work_item(configuration: ApplicationConfiguration) -> IncrementalReplayWorkItem:
    return IncrementalReplayWorkItem.create(
        trading_date="20221106",
        source_sha256=configuration.source_sha256,
        discovery_checkpoint_sha256="2" * 64,
        case_ids=configuration.case_ids,
        affected_case_ids=("affected",),
    )


def _partial() -> CanonicalPartialCaseSurfaces:
    return CanonicalPartialCaseSurfaces(
        "affected",
        "20221106",
        "TP1",
        {surface: f"{surface}\n".encode() for surface in sorted(PARTIAL_E2E_SURFACES)},
    )


def test_progress_round_trips_exact_continuation_state(tmp_path) -> None:
    configuration = _configuration(tmp_path)
    work_item = _work_item(configuration)
    progress = PyspdReplayProgress.create(
        work_item_sha256=work_item.logical_sha256,
        application_configuration_sha256=configuration.logical_sha256,
        execution_source_sha256=EXECUTION_SHA256,
        next_case_ordinal=1,
        last_completed_case_id="warmup",
        previous_generation={"G1": 12.5},
        event_sequence=7,
        energy_numerator={("TP1", "N1"): 15000.25},
        reserve_numerator={("TP1", "NI", "FIR"): 100.5},
        total_seconds={"TP1": 300.0},
        period_date_time={"TP1": "06-NOV-2022 00:00"},
    )
    store = PyspdReplayProgressStore(tmp_path / "progress", "20221106")

    store.write_checkpoint(progress)
    loaded = store.load(
        work_item, configuration, execution_source_sha256=EXECUTION_SHA256
    )

    assert loaded == progress
    assert loaded is not None
    assert loaded.energy_numerator[("TP1", "N1")].hex() == (15000.25).hex()
    assert loaded.period_date_time == {"TP1": "06-NOV-2022 00:00"}


def test_progress_rejects_work_item_drift(tmp_path) -> None:
    configuration = _configuration(tmp_path)
    work_item = _work_item(configuration)
    progress = PyspdReplayProgress.create(
        work_item_sha256=work_item.logical_sha256,
        application_configuration_sha256=configuration.logical_sha256,
        execution_source_sha256=EXECUTION_SHA256,
    )
    store = PyspdReplayProgressStore(tmp_path / "progress", "20221106")
    store.write_checkpoint(progress)
    changed = IncrementalReplayWorkItem.create(
        trading_date="20221106",
        source_sha256=configuration.source_sha256,
        discovery_checkpoint_sha256="3" * 64,
        case_ids=configuration.case_ids,
        affected_case_ids=("affected",),
    )

    with pytest.raises(EvidenceContractError, match="provenance or position"):
        store.load(changed, configuration, execution_source_sha256=EXECUTION_SHA256)


def test_progress_rejects_execution_source_drift(tmp_path) -> None:
    configuration = _configuration(tmp_path)
    work_item = _work_item(configuration)
    progress = PyspdReplayProgress.create(
        work_item_sha256=work_item.logical_sha256,
        application_configuration_sha256=configuration.logical_sha256,
        execution_source_sha256=EXECUTION_SHA256,
    )
    store = PyspdReplayProgressStore(tmp_path / "progress", "20221106")
    store.write_checkpoint(progress)

    with pytest.raises(EvidenceContractError, match="provenance or position"):
        store.load(work_item, configuration, execution_source_sha256="f" * 64)


def test_progress_load_rejects_tampered_partial_case_evidence(tmp_path) -> None:
    configuration = _configuration(tmp_path)
    work_item = _work_item(configuration)
    partial = _partial()
    store = PyspdReplayProgressStore(tmp_path / "progress", "20221106")
    store.write_partial(partial)
    progress = PyspdReplayProgress.create(
        work_item_sha256=work_item.logical_sha256,
        application_configuration_sha256=configuration.logical_sha256,
        execution_source_sha256=EXECUTION_SHA256,
        next_case_ordinal=2,
        last_completed_case_id="affected",
        partial_surface_sha256={"affected": partial.surface_sha256},
        partial_trading_period={"affected": "TP1"},
    )
    store.write_checkpoint(progress)
    tampered = (
        tmp_path / "progress" / "20221106" / "cases" / "affected" / "node-price.json"
    )
    tampered.write_bytes(b"tampered\n")

    with pytest.raises(EvidenceContractError, match="evidence hash mismatch"):
        store.load(work_item, configuration, execution_source_sha256=EXECUTION_SHA256)


class _InterruptingCaseRunner:
    def __init__(self, cases) -> None:
        observations = [make_observation(case) for case in cases]
        self.delegate = DailyCaseRunner(SequenceExecutor(observations))
        self.failure_case_id: str | None = "affected"
        self.attempts: list[str] = []

    def execute(self, configuration, prepared, **kwargs):
        case_id = prepared.specification.case_id
        self.attempts.append(case_id)
        if case_id == self.failure_case_id:
            raise RuntimeError("simulated interruption")
        return self.delegate.execute(configuration, prepared, **kwargs)


class _StreamingTestApplication:
    def __init__(self, configuration: ApplicationConfiguration) -> None:
        self.configuration = configuration
        self.cases = tuple(
            make_daily_case(
                case_id,
                trading_period="TP1",
                ordinal=ordinal,
                seconds=300.0,
            )
            for ordinal, case_id in enumerate(configuration.case_ids)
        )
        self.cases = tuple(
            replace(case, source_sha256=configuration.source_sha256)
            for case in self.cases
        )
        self.runner = _InterruptingCaseRunner(self.cases)
        self.start_ordinals: list[int] = []

    def daily_configuration(self, configuration):
        return DailyRunConfiguration(
            configuration.formulation_id,
            configuration.source_sha256,
            maximum_solve_loops=configuration.maximum_solve_loops,
            price_rounding_decimals=configuration.price_rounding_decimals,
            environment_fingerprint="test-arm64",
            application_configuration_sha256=configuration.logical_sha256,
        )

    def case_runner(self, configuration):
        del configuration
        return self.runner

    def iter_prepared_cases(self, configuration, *, start_ordinal=0):
        del configuration
        self.start_ordinals.append(start_ordinal)
        for case in self.cases[start_ordinal:]:
            yield make_prepared(case)

    def render_report_bundle(self, configuration, result):
        profile = daily_report_registry().resolve(configuration.formulation_id)
        provenance = ArtifactProvenance(
            configuration.formulation_id,
            configuration.source_sha256,
            result.configuration_sha256,
            "test",
            "1" * 64,
            configuration.solver_profile,
            "test-arm64",
        )
        return profile.report_renderer().render(
            profile.result_schema().collect(result, provenance)
        )


def test_streaming_runner_resumes_after_last_durable_case(tmp_path) -> None:
    configuration = _configuration(tmp_path)
    work_item = _work_item(configuration)
    application = _StreamingTestApplication(configuration)
    runner = StreamingPyspdReplayRunner(application=application)  # type: ignore[arg-type]
    progress_root = tmp_path / "progress"

    with pytest.raises(RuntimeError, match="simulated interruption"):
        runner.run(
            configuration=configuration,
            work_item=work_item,
            progress_root=progress_root,
        )
    application.runner.failure_case_id = None
    cases = runner.run(
        configuration=configuration,
        work_item=work_item,
        progress_root=progress_root,
    )

    assert application.start_ordinals == [0, 1]
    assert application.runner.attempts == ["warmup", "affected", "affected"]
    assert tuple(case.case_id for case in cases) == ("affected",)
    assert set(cases[0].surfaces) == set(REQUIRED_E2E_SURFACES)
    progress = PyspdReplayProgressStore(progress_root, "20221106").load(
        work_item,
        configuration,
        execution_source_sha256=python_execution_sha256(),
    )
    assert progress is not None
    assert progress.next_case_ordinal == 2
