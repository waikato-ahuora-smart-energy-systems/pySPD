"""Checkpoint-driven, incremental Gate 12 replay and parity orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.historical_population import (
    HISTORICAL_EXECUTION_PROFILE,
    HistoricalCaseIndexLoader,
    HistoricalGdxCaseIndex,
    HistoricalInputArtifact,
    HistoricalInputInventory,
    HistoricalPopulationCheckpoint,
    HistoricalPopulationCheckpointStore,
)

INCREMENTAL_REPLAY_POLICY = "canonical-same-day-prefix-through-last-affected-case"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TRADING_DATE = re.compile(r"[0-9]{8}")


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class IncrementalReplayWorkItem:
    """One immutable daily prefix ready for reference and candidate replay."""

    trading_date: str
    source_sha256: str
    discovery_checkpoint_sha256: str
    case_ids: tuple[str, ...]
    affected_case_ids: tuple[str, ...]
    logical_sha256: str

    @classmethod
    def create(
        cls,
        *,
        trading_date: str,
        source_sha256: str,
        discovery_checkpoint_sha256: str,
        case_ids: tuple[str, ...],
        affected_case_ids: tuple[str, ...],
    ) -> IncrementalReplayWorkItem:
        unsigned = {
            "schema_version": 1,
            "policy": INCREMENTAL_REPLAY_POLICY,
            "trading_date": trading_date,
            "source_sha256": source_sha256,
            "discovery_checkpoint_sha256": discovery_checkpoint_sha256,
            "case_ids": list(case_ids),
            "affected_case_ids": list(affected_case_ids),
        }
        item = cls(
            trading_date=trading_date,
            source_sha256=source_sha256,
            discovery_checkpoint_sha256=discovery_checkpoint_sha256,
            case_ids=case_ids,
            affected_case_ids=affected_case_ids,
            logical_sha256=_logical_sha256(unsigned),
        )
        item.validate()
        return item

    def validate(self) -> None:
        hashes = (self.source_sha256, self.discovery_checkpoint_sha256)
        if (
            not _TRADING_DATE.fullmatch(self.trading_date)
            or any(not _SHA256.fullmatch(value) for value in hashes)
            or not self.case_ids
            or not self.affected_case_ids
            or len(set(self.case_ids)) != len(self.case_ids)
            or len(set(self.affected_case_ids)) != len(self.affected_case_ids)
            or not set(self.affected_case_ids).issubset(self.case_ids)
        ):
            raise EvidenceContractError("REQ-G12-INCREMENTAL: invalid replay work item")
        unsigned = self.to_dict(include_hash=False)
        if self.logical_sha256 != _logical_sha256(unsigned):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: replay work-item hash mismatch"
            )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "policy": INCREMENTAL_REPLAY_POLICY,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "discovery_checkpoint_sha256": self.discovery_checkpoint_sha256,
            "case_ids": list(self.case_ids),
            "affected_case_ids": list(self.affected_case_ids),
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class HistoricalCheckpointReplayPlanner:
    """Derive one canonical replay prefix from a qualified daily checkpoint."""

    def plan(
        self,
        *,
        checkpoint: HistoricalPopulationCheckpoint,
        artifact: HistoricalInputArtifact,
        index: HistoricalGdxCaseIndex,
    ) -> IncrementalReplayWorkItem:
        if (
            checkpoint.trading_date != artifact.trading_date
            or checkpoint.source_sha256 != artifact.sha256
            or checkpoint.solver_profile != HISTORICAL_EXECUTION_PROFILE
            or not checkpoint.all_solves_optimal
            or checkpoint.solved_case_count != checkpoint.selected_case_count
        ):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: discovery checkpoint provenance mismatch"
            )
        affected = set(checkpoint.evidence.affected_cases)
        if not affected:
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: governed affected date has no affected case"
            )
        positions = {
            identity: position for position, identity in enumerate(index.cases)
        }
        if not affected.issubset(positions):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: affected identity is absent from canonical GDX"
            )
        ordered = tuple(sorted(affected, key=positions.__getitem__))
        last_position = positions[ordered[-1]]
        prefix = index.cases[: last_position + 1]
        prefix_case_ids = tuple(case_id for case_id, _ in prefix)
        affected_case_ids = tuple(case_id for case_id, _ in ordered)
        if len(set(prefix_case_ids)) != len(prefix_case_ids):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: canonical prefix contains duplicate case IDs"
            )
        return IncrementalReplayWorkItem.create(
            trading_date=artifact.trading_date,
            source_sha256=artifact.sha256,
            discovery_checkpoint_sha256=checkpoint.logical_sha256,
            case_ids=prefix_case_ids,
            affected_case_ids=affected_case_ids,
        )


@dataclass(frozen=True, slots=True)
class IncrementalCaseParity:
    """Comparison hashes and disposition for one affected interval."""

    case_id: str
    reference_surface_sha256: dict[str, str]
    candidate_surface_sha256: dict[str, str]
    unresolved_material_count: int
    passed: bool

    def validate(self) -> None:
        hashes = (
            *self.reference_surface_sha256.values(),
            *self.candidate_surface_sha256.values(),
        )
        if (
            not self.case_id.strip()
            or set(self.reference_surface_sha256) != set(REQUIRED_E2E_SURFACES)
            or set(self.candidate_surface_sha256) != set(REQUIRED_E2E_SURFACES)
            or any(not _SHA256.fullmatch(value) for value in hashes)
            or not isinstance(self.unresolved_material_count, int)
            or isinstance(self.unresolved_material_count, bool)
            or self.unresolved_material_count < 0
            or self.passed != (self.unresolved_material_count == 0)
        ):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: invalid affected-case parity result"
            )


@dataclass(frozen=True, slots=True)
class IncrementalDateParityResult:
    """Processor result for both sides of one prefix-complete daily replay."""

    processor_profile: str
    reference_artifact_sha256: str
    candidate_artifact_sha256: str
    cases: tuple[IncrementalCaseParity, ...]

    @property
    def passed(self) -> bool:
        return bool(self.cases and all(case.passed for case in self.cases))

    @property
    def unresolved_material_count(self) -> int:
        return sum(case.unresolved_material_count for case in self.cases)

    def validate(self, *, expected_case_ids: tuple[str, ...]) -> None:
        case_ids = tuple(case.case_id for case in self.cases)
        if (
            not self.processor_profile.strip()
            or not _SHA256.fullmatch(self.reference_artifact_sha256)
            or not _SHA256.fullmatch(self.candidate_artifact_sha256)
            or case_ids != expected_case_ids
            or len(set(case_ids)) != len(case_ids)
        ):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: parity result identity or provenance mismatch"
            )
        for case in self.cases:
            case.validate()


class IncrementalDateParityProcessor(Protocol):
    """Run both replay engines and compare one immutable work item."""

    profile: str

    def process(
        self,
        *,
        work_item: IncrementalReplayWorkItem,
        source: Path,
        system_directory: Path,
    ) -> IncrementalDateParityResult: ...


@dataclass(frozen=True, slots=True)
class IncrementalAvailableWork:
    """A validated source and work item exposed by the discovery feed."""

    work_item: IncrementalReplayWorkItem
    source: Path


class IncrementalDiscoveryFeed:
    """Expose only the contiguous prefix of immutable discovery checkpoints."""

    def __init__(
        self,
        *,
        inventory: HistoricalInputInventory,
        input_root: Path,
        system_directory: Path,
        discovery_store: HistoricalPopulationCheckpointStore,
        index_loader: HistoricalCaseIndexLoader,
        planner: HistoricalCheckpointReplayPlanner | None = None,
    ) -> None:
        self.inventory = inventory
        self.input_root = input_root
        self.system_directory = system_directory
        self.discovery_store = discovery_store
        self.index_loader = index_loader
        self.planner = planner or HistoricalCheckpointReplayPlanner()

    def scan(self) -> tuple[tuple[IncrementalAvailableWork, ...], str | None]:
        available = []
        waiting: str | None = None
        for artifact in self.inventory.artifacts:
            checkpoint = self.discovery_store.load(artifact.trading_date)
            if checkpoint is None:
                waiting = artifact.trading_date
                break
            source = self._validated_source(artifact)
            index = self.index_loader.load(source, self.system_directory)
            work_item = self.planner.plan(
                checkpoint=checkpoint,
                artifact=artifact,
                index=index,
            )
            available.append(IncrementalAvailableWork(work_item, source))
        return tuple(available), waiting

    def _validated_source(self, artifact: HistoricalInputArtifact) -> Path:
        source = (
            self.input_root
            / artifact.trading_date[:4]
            / f"Pricing_{artifact.trading_date}.gdx"
        )
        try:
            size = source.stat().st_size
        except OSError as error:
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: governed replay source is unavailable"
            ) from error
        if size != artifact.size_bytes or _file_sha256(source) != artifact.sha256:
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: governed replay source hash or size mismatch"
            )
        return source


@dataclass(frozen=True, slots=True)
class IncrementalParityCheckpoint:
    """Atomic, resumable evidence for one completed daily comparison."""

    trading_date: str
    source_sha256: str
    discovery_checkpoint_sha256: str
    work_item_sha256: str
    processor_profile: str
    reference_artifact_sha256: str
    candidate_artifact_sha256: str
    cases: tuple[IncrementalCaseParity, ...]
    passed: bool
    unresolved_material_count: int
    logical_sha256: str

    @classmethod
    def create(
        cls,
        *,
        work_item: IncrementalReplayWorkItem,
        result: IncrementalDateParityResult,
    ) -> IncrementalParityCheckpoint:
        result.validate(expected_case_ids=work_item.affected_case_ids)
        unsigned = {
            "schema_version": 1,
            "trading_date": work_item.trading_date,
            "source_sha256": work_item.source_sha256,
            "discovery_checkpoint_sha256": work_item.discovery_checkpoint_sha256,
            "work_item_sha256": work_item.logical_sha256,
            "processor_profile": result.processor_profile,
            "reference_artifact_sha256": result.reference_artifact_sha256,
            "candidate_artifact_sha256": result.candidate_artifact_sha256,
            "cases": [_case_to_dict(case) for case in result.cases],
            "passed": result.passed,
            "unresolved_material_count": result.unresolved_material_count,
        }
        return cls(
            trading_date=work_item.trading_date,
            source_sha256=work_item.source_sha256,
            discovery_checkpoint_sha256=work_item.discovery_checkpoint_sha256,
            work_item_sha256=work_item.logical_sha256,
            processor_profile=result.processor_profile,
            reference_artifact_sha256=result.reference_artifact_sha256,
            candidate_artifact_sha256=result.candidate_artifact_sha256,
            cases=result.cases,
            passed=result.passed,
            unresolved_material_count=result.unresolved_material_count,
            logical_sha256=_logical_sha256(unsigned),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> IncrementalParityCheckpoint:
        expected = {
            "schema_version",
            "trading_date",
            "source_sha256",
            "discovery_checkpoint_sha256",
            "work_item_sha256",
            "processor_profile",
            "reference_artifact_sha256",
            "candidate_artifact_sha256",
            "cases",
            "passed",
            "unresolved_material_count",
            "logical_sha256",
        }
        if set(payload) != expected or payload.get("schema_version") != 1:
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: unexpected parity checkpoint schema"
            )
        try:
            cases = tuple(
                IncrementalCaseParity(
                    case_id=item["case_id"],
                    reference_surface_sha256=item["reference_surface_sha256"],
                    candidate_surface_sha256=item["candidate_surface_sha256"],
                    unresolved_material_count=item["unresolved_material_count"],
                    passed=item["passed"],
                )
                for item in payload["cases"]
            )
            checkpoint = cls(
                trading_date=payload["trading_date"],
                source_sha256=payload["source_sha256"],
                discovery_checkpoint_sha256=payload["discovery_checkpoint_sha256"],
                work_item_sha256=payload["work_item_sha256"],
                processor_profile=payload["processor_profile"],
                reference_artifact_sha256=payload["reference_artifact_sha256"],
                candidate_artifact_sha256=payload["candidate_artifact_sha256"],
                cases=cases,
                passed=payload["passed"],
                unresolved_material_count=payload["unresolved_material_count"],
                logical_sha256=payload["logical_sha256"],
            )
        except (KeyError, TypeError) as error:
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: invalid parity checkpoint"
            ) from error
        checkpoint.validate()
        return checkpoint

    def validate(self) -> None:
        result = IncrementalDateParityResult(
            processor_profile=self.processor_profile,
            reference_artifact_sha256=self.reference_artifact_sha256,
            candidate_artifact_sha256=self.candidate_artifact_sha256,
            cases=self.cases,
        )
        result.validate(expected_case_ids=tuple(case.case_id for case in self.cases))
        hashes = (
            self.source_sha256,
            self.discovery_checkpoint_sha256,
            self.work_item_sha256,
            self.logical_sha256,
        )
        if (
            not _TRADING_DATE.fullmatch(self.trading_date)
            or any(not _SHA256.fullmatch(value) for value in hashes)
            or self.passed != result.passed
            or self.unresolved_material_count != result.unresolved_material_count
        ):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: invalid parity checkpoint values"
            )
        unsigned = self.to_dict(include_hash=False)
        if self.logical_sha256 != _logical_sha256(unsigned):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: parity checkpoint hash mismatch"
            )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "discovery_checkpoint_sha256": self.discovery_checkpoint_sha256,
            "work_item_sha256": self.work_item_sha256,
            "processor_profile": self.processor_profile,
            "reference_artifact_sha256": self.reference_artifact_sha256,
            "candidate_artifact_sha256": self.candidate_artifact_sha256,
            "cases": [_case_to_dict(case) for case in self.cases],
            "passed": self.passed,
            "unresolved_material_count": self.unresolved_material_count,
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


def _case_to_dict(case: IncrementalCaseParity) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "reference_surface_sha256": case.reference_surface_sha256,
        "candidate_surface_sha256": case.candidate_surface_sha256,
        "unresolved_material_count": case.unresolved_material_count,
        "passed": case.passed,
    }


class IncrementalParityCheckpointStore:
    """Atomically persist date-level parity evidence and reject stale reuse."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, trading_date: str) -> IncrementalParityCheckpoint | None:
        path = self._path(trading_date)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: unreadable parity checkpoint"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: parity checkpoint must be an object"
            )
        return IncrementalParityCheckpoint.from_dict(payload)

    def write(self, checkpoint: IncrementalParityCheckpoint) -> Path:
        checkpoint.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(checkpoint.trading_date)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(checkpoint.to_dict(), sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def reusable(
        self,
        *,
        work_item: IncrementalReplayWorkItem,
        processor_profile: str,
    ) -> bool:
        checkpoint = self.load(work_item.trading_date)
        return bool(
            checkpoint is not None
            and checkpoint.source_sha256 == work_item.source_sha256
            and checkpoint.discovery_checkpoint_sha256
            == work_item.discovery_checkpoint_sha256
            and checkpoint.work_item_sha256 == work_item.logical_sha256
            and checkpoint.processor_profile == processor_profile
            and checkpoint.passed
            and checkpoint.unresolved_material_count == 0
        )

    def _path(self, trading_date: str) -> Path:
        if not _TRADING_DATE.fullmatch(trading_date):
            raise EvidenceContractError(
                "REQ-G12-INCREMENTAL: invalid parity checkpoint date"
            )
        return self.root / f"{trading_date}.json"


@dataclass(frozen=True, slots=True)
class IncrementalParityRunSummary:
    """Bounded progress snapshot for all currently available discovery dates."""

    available_date_count: int
    parity_checkpoint_count: int
    processed_date_count: int
    affected_case_count: int
    unresolved_material_count: int
    waiting_for_trading_date: str | None


class IncrementalGate12Coordinator:
    """Process each newly available discovery checkpoint once, in source order."""

    def __init__(
        self,
        *,
        inventory: HistoricalInputInventory,
        input_root: Path,
        system_directory: Path,
        discovery_store: HistoricalPopulationCheckpointStore,
        parity_store: IncrementalParityCheckpointStore,
        index_loader: HistoricalCaseIndexLoader,
        processor: IncrementalDateParityProcessor,
        planner: HistoricalCheckpointReplayPlanner | None = None,
    ) -> None:
        self.feed = IncrementalDiscoveryFeed(
            inventory=inventory,
            input_root=input_root,
            system_directory=system_directory,
            discovery_store=discovery_store,
            index_loader=index_loader,
            planner=planner,
        )
        self.inventory = self.feed.inventory
        self.input_root = self.feed.input_root
        self.system_directory = self.feed.system_directory
        self.discovery_store = self.feed.discovery_store
        self.parity_store = parity_store
        self.index_loader = self.feed.index_loader
        self.processor = processor
        self.planner = self.feed.planner

    def run_available(self) -> IncrementalParityRunSummary:
        processed = affected = unresolved = 0
        available_work, waiting = self.feed.scan()
        for available in available_work:
            work_item = available.work_item
            affected += len(work_item.affected_case_ids)
            if self.parity_store.reusable(
                work_item=work_item, processor_profile=self.processor.profile
            ):
                continue
            result = self.processor.process(
                work_item=work_item,
                source=available.source,
                system_directory=self.system_directory,
            )
            if result.processor_profile != self.processor.profile:
                raise EvidenceContractError(
                    "REQ-G12-INCREMENTAL: processor profile mismatch"
                )
            parity_checkpoint = IncrementalParityCheckpoint.create(
                work_item=work_item, result=result
            )
            self.parity_store.write(parity_checkpoint)
            processed += 1
            unresolved += parity_checkpoint.unresolved_material_count
            if not parity_checkpoint.passed:
                raise EvidenceContractError(
                    "REQ-G12-INCREMENTAL: daily parity comparison failed for "
                    f"{work_item.trading_date}"
                )
        completed = sum(
            self.parity_store.load(artifact.trading_date) is not None
            for artifact in self.inventory.artifacts[: len(available_work)]
        )
        return IncrementalParityRunSummary(
            available_date_count=len(available_work),
            parity_checkpoint_count=completed,
            processed_date_count=processed,
            affected_case_count=affected,
            unresolved_material_count=unresolved,
            waiting_for_trading_date=waiting,
        )
