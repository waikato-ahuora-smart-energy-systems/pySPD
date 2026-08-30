"""Probity tests for checkpoint-driven Gate 12 replay processing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.historical_population import (
    HISTORICAL_EXECUTION_PROFILE,
    HistoricalGdxCaseIndex,
    HistoricalInputArtifact,
    HistoricalInputInventory,
    HistoricalPopulationCheckpoint,
    HistoricalPopulationCheckpointStore,
    HistoricalShortfallEvidence,
)
from tools.gate12.incremental_replay import (
    HistoricalCheckpointReplayPlanner,
    IncrementalCaseParity,
    IncrementalDateParityResult,
    IncrementalGate12Coordinator,
    IncrementalParityCheckpointStore,
)

HEADER = (
    "case_id|datetime|node|target_node|loop|energy_shortfall_mw|adjustment_mw|"
    "model_status|solver_status\n"
)


def _checkpoint(
    trading_date: str,
    source_sha256: str,
    *,
    cases: tuple[tuple[str, str], ...],
) -> HistoricalPopulationCheckpoint:
    rows = "".join(
        f"{case_id}|{date_time}|SRC|DST|1|1.0|1.0|1|1\n" for case_id, date_time in cases
    )
    evidence = HistoricalShortfallEvidence.parse(
        HEADER + rows, source_name=f"Pricing_{trading_date}"
    )
    return HistoricalPopulationCheckpoint.create(
        trading_date=trading_date,
        source_sha256=source_sha256,
        patch_sha256="a" * 64,
        solver_profile=HISTORICAL_EXECUTION_PROFILE,
        selected_case_count=4,
        solved_case_count=4,
        all_solves_optimal=True,
        artifact_sha256={
            "progress": "b" * 64,
            "listing": "c" * 64,
            "evidence": "d" * 64,
        },
        evidence=evidence,
    )


class FakeIndexLoader:
    def __init__(self, indices: dict[str, HistoricalGdxCaseIndex]) -> None:
        self.indices = indices
        self.loaded: list[str] = []

    def load(self, path: Path, system_directory: Path) -> HistoricalGdxCaseIndex:
        del system_directory
        trading_date = path.stem.removeprefix("Pricing_")
        self.loaded.append(trading_date)
        return self.indices[trading_date]


class FakeProcessor:
    profile = "test-gams-reference+pyspd-candidate-v1"

    def __init__(self, *, fail_date: str | None = None) -> None:
        self.fail_date = fail_date
        self.processed: list[str] = []

    def process(self, *, work_item, source: Path, system_directory: Path):
        del source, system_directory
        self.processed.append(work_item.trading_date)
        failed = work_item.trading_date == self.fail_date
        reference = {name: "1" * 64 for name in REQUIRED_E2E_SURFACES}
        candidate = dict(reference)
        if failed:
            candidate["node-price"] = "2" * 64
        return IncrementalDateParityResult(
            processor_profile=self.profile,
            reference_artifact_sha256="3" * 64,
            candidate_artifact_sha256="4" * 64,
            cases=tuple(
                IncrementalCaseParity(
                    case_id=case_id,
                    reference_surface_sha256=reference,
                    candidate_surface_sha256=candidate,
                    unresolved_material_count=int(failed),
                    passed=not failed,
                )
                for case_id in work_item.affected_case_ids
            ),
        )


def _fixture(tmp_path: Path):
    dates = ("20221106", "20221107", "20221109")
    artifacts = []
    indices = {}
    discovery = HistoricalPopulationCheckpointStore(tmp_path / "discovery")
    for offset, trading_date in enumerate(dates):
        content = f"gdx-{trading_date}".encode()
        source = tmp_path / "inputs" / "2022" / f"Pricing_{trading_date}.gdx"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        source_hash = hashlib.sha256(content).hexdigest()
        artifacts.append(
            HistoricalInputArtifact(trading_date, len(content), source_hash)
        )
        cases = tuple(
            (f"case-{offset}-{index}", f"DT-{offset}-{index}") for index in range(4)
        )
        indices[trading_date] = HistoricalGdxCaseIndex(
            cases=cases,
            trading_periods={
                case: f"TP{index + 1}" for index, case in enumerate(cases)
            },
        )
        if offset < 2:
            discovery.write(
                _checkpoint(trading_date, source_hash, cases=(cases[1], cases[3]))
            )
    return (
        HistoricalInputInventory(tuple(artifacts)),
        indices,
        discovery,
    )


def _coordinator(
    tmp_path: Path,
    *,
    processor: FakeProcessor,
    stop_on_discrepancy: bool = True,
) -> tuple[IncrementalGate12Coordinator, HistoricalPopulationCheckpointStore]:
    inventory, indices, discovery = _fixture(tmp_path)
    coordinator = IncrementalGate12Coordinator(
        inventory=inventory,
        input_root=tmp_path / "inputs",
        system_directory=tmp_path / "gams",
        discovery_store=discovery,
        parity_store=IncrementalParityCheckpointStore(tmp_path / "parity"),
        index_loader=FakeIndexLoader(indices),
        processor=processor,
        stop_on_discrepancy=stop_on_discrepancy,
    )
    return coordinator, discovery


def test_incremental_planner_preserves_prefix_through_last_affected_case() -> None:
    source_hash = "1" * 64
    cases = tuple((f"case-{index}", f"DT-{index}") for index in range(5))
    index = HistoricalGdxCaseIndex(
        cases=cases,
        trading_periods={case: f"TP{index + 1}" for index, case in enumerate(cases)},
    )
    checkpoint = _checkpoint("20221106", source_hash, cases=(cases[1], cases[3]))

    work_item = HistoricalCheckpointReplayPlanner().plan(
        checkpoint=checkpoint,
        artifact=HistoricalInputArtifact("20221106", 1, source_hash),
        index=index,
    )

    assert work_item.case_ids == tuple(case_id for case_id, _ in cases[:4])
    assert work_item.affected_case_ids == ("case-1", "case-3")
    assert len(work_item.logical_sha256) == 64


def test_coordinator_processes_available_prefix_and_resumes_once(
    tmp_path: Path,
) -> None:
    processor = FakeProcessor()
    coordinator, discovery = _coordinator(tmp_path, processor=processor)

    first = coordinator.run_available()
    second = coordinator.run_available()

    assert first.available_date_count == 2
    assert first.parity_checkpoint_count == 2
    assert first.processed_date_count == 2
    assert first.affected_case_count == 4
    assert first.waiting_for_trading_date == "20221109"
    assert second.processed_date_count == 0
    assert processor.processed == ["20221106", "20221107"]

    inventory = coordinator.inventory
    artifact = inventory.artifacts[2]
    cases = coordinator.index_loader.indices[artifact.trading_date]  # type: ignore[attr-defined]
    discovery.write(
        _checkpoint(
            artifact.trading_date,
            artifact.sha256,
            cases=(cases.cases[1], cases.cases[3]),
        )
    )
    third = coordinator.run_available()

    assert third.available_date_count == 3
    assert third.parity_checkpoint_count == 3
    assert third.processed_date_count == 1
    assert third.waiting_for_trading_date is None
    assert processor.processed[-1] == "20221109"


def test_coordinator_does_not_skip_a_missing_earlier_checkpoint(
    tmp_path: Path,
) -> None:
    processor = FakeProcessor()
    coordinator, discovery = _coordinator(tmp_path, processor=processor)
    first_date = coordinator.inventory.artifacts[0].trading_date
    (discovery.root / f"{first_date}.json").unlink()

    summary = coordinator.run_available()

    assert summary.available_date_count == 0
    assert summary.processed_date_count == 0
    assert summary.waiting_for_trading_date == first_date
    assert processor.processed == []


def test_coordinator_persists_failed_parity_and_stops(tmp_path: Path) -> None:
    processor = FakeProcessor(fail_date="20221107")
    coordinator, _ = _coordinator(tmp_path, processor=processor)

    with pytest.raises(EvidenceContractError, match="daily parity.*20221107"):
        coordinator.run_available()

    first = coordinator.parity_store.load("20221106")
    failed = coordinator.parity_store.load("20221107")
    assert first is not None and first.passed
    assert failed is not None and not failed.passed
    assert failed.unresolved_material_count == 2


def test_observation_mode_records_later_dates_and_reuses_failed_evidence(
    tmp_path: Path,
) -> None:
    processor = FakeProcessor(fail_date="20221106")
    coordinator, _ = _coordinator(
        tmp_path, processor=processor, stop_on_discrepancy=False
    )

    first = coordinator.run_available()
    second = coordinator.run_available()

    assert processor.processed == ["20221106", "20221107"]
    assert first.processed_date_count == 2
    assert first.failed_date_count == 1
    assert first.unresolved_material_count == 2
    assert first.parity_checkpoint_count == 2
    assert second.processed_date_count == 0
    assert second.failed_date_count == 1
    assert second.unresolved_material_count == 2


def test_coordinator_rejects_source_drift_before_replay(tmp_path: Path) -> None:
    processor = FakeProcessor()
    coordinator, _ = _coordinator(tmp_path, processor=processor)
    first = coordinator.inventory.artifacts[0]
    source = tmp_path / "inputs" / "2022" / f"Pricing_{first.trading_date}.gdx"
    source.write_bytes(b"drift")

    with pytest.raises(EvidenceContractError, match="source hash or size"):
        coordinator.run_available()

    assert processor.processed == []


def test_failed_checkpoint_is_not_reused_as_a_pass(tmp_path: Path) -> None:
    processor = FakeProcessor(fail_date="20221106")
    coordinator, _ = _coordinator(tmp_path, processor=processor)

    with pytest.raises(EvidenceContractError, match="daily parity"):
        coordinator.run_available()
    with pytest.raises(EvidenceContractError, match="daily parity"):
        coordinator.run_available()

    assert processor.processed == ["20221106", "20221106"]
