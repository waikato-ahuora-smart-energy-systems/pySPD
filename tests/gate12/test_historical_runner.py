"""Probity tests for resumable Gate 12 historical enumeration."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import (
    HISTORICAL_EXECUTION_PROFILE,
    HistoricalGdxCaseIndex,
    HistoricalInputArtifact,
    HistoricalInputInventory,
    HistoricalPatchEvidence,
    HistoricalPopulationCheckpointStore,
    HistoricalPopulationRunner,
    HistoricalPopulationWorkspace,
)

HEADER = (
    "case_id|datetime|node|loop|energy_shortfall_mw|adjustment_mw|"
    "model_status|solver_status\n"
)


class FakeIndexLoader:
    def load(self, path: Path, system_directory: Path) -> HistoricalGdxCaseIndex:
        del path, system_directory
        return HistoricalGdxCaseIndex(
            cases=(("case_1", "06-NOV-2022 07:00"),),
            trading_periods={
                ("case_1", "06-NOV-2022 07:00"): "TP15",
            },
        )


class FakeGamsExecutor:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def execute(
        self, executable: Path, programs: Path, arguments: tuple[str, ...]
    ) -> None:
        del executable
        self.commands.append(arguments)
        if arguments[0] == "vSPDsolve.gms":
            (programs / "ProgressReport.txt").write_text(
                "The caseID: case_1 (06-NOV-2022 07:00) "
                "is 1st solved successfully.\n"
            )
            (programs / "gate12_Pricing_20221106_shortfall.txt").write_text(
                HEADER + "case_1|06-NOV-2022 07:00|WAI0111|1|4.5|4.5|1|1\n"
            )
            (programs / "vSPDsolve.lst").write_text(
                "Solution Report     SOLVE vSPD_NMIR Using MIP\n"
                "SOLVER SCIP\n"
                "**** SOLVER STATUS     1 Normal Completion\n"
                "**** MODEL STATUS      1 Optimal\n"
                "**** OBJECTIVE VALUE                1.0000\n"
            )


def _runner(tmp_path: Path) -> tuple[HistoricalPopulationRunner, FakeGamsExecutor]:
    programs = tmp_path / "vspd" / "Programs"
    programs.mkdir(parents=True)
    files = {}
    for name in ("vSPDsettings.inc", "vSPDperiod.gms", "vSPDsolve.gms"):
        path = programs / name
        path.write_text(name)
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    patch = HistoricalPatchEvidence(
        profile="historical-v5.0.2-scip-first-loop",
        logical_sha256=hashlib.sha256(b"patch").hexdigest(),
        file_sha256=files,
    )
    source = tmp_path / "inputs" / "2022" / "Pricing_20221106.gdx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"gdx")
    artifact = HistoricalInputArtifact(
        trading_date="20221106",
        size_bytes=3,
        sha256=hashlib.sha256(b"gdx").hexdigest(),
    )
    executor = FakeGamsExecutor()
    runner = HistoricalPopulationRunner(
        programs=programs,
        input_root=tmp_path / "inputs",
        inventory=HistoricalInputInventory((artifact,)),
        system_directory=tmp_path / "gams",
        gams_executable=tmp_path / "gams" / "gams",
        patch_evidence=patch,
        checkpoint_store=HistoricalPopulationCheckpointStore(
            tmp_path / "checkpoints"
        ),
        index_loader=FakeIndexLoader(),
        executor=executor,
    )
    return runner, executor


def test_population_runner_executes_and_resumes_by_checkpoint(tmp_path: Path) -> None:
    assert "rtd-only" in HISTORICAL_EXECUTION_PROFILE
    runner, executor = _runner(tmp_path)

    first = runner.run()
    second = runner.run()

    assert len(first) == len(second) == 1
    assert first[0].logical_sha256 == second[0].logical_sha256
    assert [command[0] for command in executor.commands] == [
        "vSPDmodel.gms",
        "vSPDperiod.gms",
        "vSPDsolve.gms",
    ]
    assert all("lo=2" in command for command in executor.commands)
    assert "solvelink=5" in executor.commands[-1]
    assert first[0].solver_profile == HISTORICAL_EXECUTION_PROFILE
    assert (runner.programs.parent / "Input" / "Pricing_20221106.gdx").is_symlink()
    assert (runner.programs / "vSPDtpsToSolve.inc").read_text() == (
        "/\ncase_1\n/\n"
    )


def test_population_runner_rejects_source_or_patch_drift(tmp_path: Path) -> None:
    runner, executor = _runner(tmp_path)
    source = runner.input_root / "2022" / "Pricing_20221106.gdx"
    source.write_bytes(b"changed")

    with pytest.raises(EvidenceContractError, match="source hash"):
        runner.run()
    assert executor.commands == []

    source.write_bytes(b"gdx")
    (runner.programs / "vSPDsolve.gms").write_text("changed")
    with pytest.raises(EvidenceContractError, match="patch hash"):
        runner.run()


class FakePatcher:
    profile = "test-profile"

    def apply(self, programs: Path) -> HistoricalPatchEvidence:
        path = programs / "vSPDsolve.gms"
        path.write_text("patched")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return HistoricalPatchEvidence(
            profile=self.profile,
            logical_sha256=hashlib.sha256(b"logical").hexdigest(),
            file_sha256={path.name: digest},
        )


def test_population_workspace_is_created_once_and_reopened(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "Programs").mkdir(parents=True)
    (source / "Programs" / "vSPDsolve.gms").write_text("original")
    root = tmp_path / "work"

    created = HistoricalPopulationWorkspace.prepare(
        source_tree=source, root=root, patcher=FakePatcher()
    )
    reopened = HistoricalPopulationWorkspace.open(root)

    assert created == reopened
    assert reopened.programs == root / "vspd" / "Programs"
    assert (reopened.programs / "vSPDsolve.gms").read_text() == "patched"
    with pytest.raises(EvidenceContractError, match="already exists"):
        HistoricalPopulationWorkspace.prepare(
            source_tree=source, root=root, patcher=FakePatcher()
        )


def test_population_workspace_rejects_metadata_tampering(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "Programs").mkdir(parents=True)
    (source / "Programs" / "vSPDsolve.gms").write_text("original")
    root = tmp_path / "work"
    HistoricalPopulationWorkspace.prepare(
        source_tree=source, root=root, patcher=FakePatcher()
    )
    metadata = root / "patch-evidence.json"
    metadata.write_text(metadata.read_text().replace("test-profile", "changed"))

    with pytest.raises(EvidenceContractError, match="metadata hash"):
        HistoricalPopulationWorkspace.open(root)


def test_population_workspace_rejects_patched_source_tampering(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "Programs").mkdir(parents=True)
    (source / "Programs" / "vSPDsolve.gms").write_text("original")
    root = tmp_path / "work"
    workspace = HistoricalPopulationWorkspace.prepare(
        source_tree=source, root=root, patcher=FakePatcher()
    )
    (workspace.programs / "vSPDsolve.gms").write_text("tampered")

    with pytest.raises(EvidenceContractError, match="patched source hash"):
        HistoricalPopulationWorkspace.open(root)
