"""Canonical replay artifacts and concrete incremental parity adapters."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pyspd.application import (
    PORTABLE_SOLVER_PROFILE,
    ApplicationConfiguration,
    PyspdApplication,
)
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.incremental_replay import (
    IncrementalCaseParity,
    IncrementalDateParityResult,
    IncrementalDiscoveryFeed,
    IncrementalReplayWorkItem,
)
from tools.gate12.pyspd_surfaces import (
    CanonicalCaseSurfaces,
    PyspdCaseSurfaceExporter,
)

PYSPD_REPLAY_PROFILE = "pyspd-v5-portable-scip-mip-fixed-highs-rmip-v1"
EXACT_CANONICAL_PARITY_PROFILE = "gams-pyspd-canonical-json-exact-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_IDENTITY = re.compile(r"[A-Za-z0-9_.-]+")


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalReplayBundle:
    """Hash index for one engine's twelve affected-case replay surfaces."""

    engine_profile: str
    trading_date: str
    source_sha256: str
    work_item_sha256: str
    affected_case_ids: tuple[str, ...]
    case_surface_sha256: dict[str, dict[str, str]]
    logical_sha256: str

    @classmethod
    def create(
        cls,
        *,
        engine_profile: str,
        work_item: IncrementalReplayWorkItem,
        cases: tuple[CanonicalCaseSurfaces, ...],
    ) -> CanonicalReplayBundle:
        case_ids = tuple(case.case_id for case in cases)
        if case_ids != work_item.affected_case_ids:
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: replay bundle case order mismatch"
            )
        surface_hashes = {case.case_id: case.surface_sha256 for case in cases}
        unsigned = {
            "schema_version": 1,
            "engine_profile": engine_profile,
            "trading_date": work_item.trading_date,
            "source_sha256": work_item.source_sha256,
            "work_item_sha256": work_item.logical_sha256,
            "affected_case_ids": list(work_item.affected_case_ids),
            "case_surface_sha256": surface_hashes,
        }
        bundle = cls(
            engine_profile=engine_profile,
            trading_date=work_item.trading_date,
            source_sha256=work_item.source_sha256,
            work_item_sha256=work_item.logical_sha256,
            affected_case_ids=work_item.affected_case_ids,
            case_surface_sha256=surface_hashes,
            logical_sha256=_logical_sha256(unsigned),
        )
        bundle.validate()
        return bundle

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CanonicalReplayBundle:
        expected = {
            "schema_version",
            "engine_profile",
            "trading_date",
            "source_sha256",
            "work_item_sha256",
            "affected_case_ids",
            "case_surface_sha256",
            "logical_sha256",
        }
        if set(payload) != expected or payload.get("schema_version") != 1:
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: unexpected replay bundle schema"
            )
        try:
            bundle = cls(
                engine_profile=payload["engine_profile"],
                trading_date=payload["trading_date"],
                source_sha256=payload["source_sha256"],
                work_item_sha256=payload["work_item_sha256"],
                affected_case_ids=tuple(payload["affected_case_ids"]),
                case_surface_sha256=payload["case_surface_sha256"],
                logical_sha256=payload["logical_sha256"],
            )
        except (TypeError, KeyError) as error:
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: invalid replay bundle"
            ) from error
        bundle.validate()
        return bundle

    def validate(self) -> None:
        if (
            not self.engine_profile.strip()
            or not re.fullmatch(r"[0-9]{8}", self.trading_date)
            or not _SHA256.fullmatch(self.source_sha256)
            or not _SHA256.fullmatch(self.work_item_sha256)
            or not _SHA256.fullmatch(self.logical_sha256)
            or not self.affected_case_ids
            or len(set(self.affected_case_ids)) != len(self.affected_case_ids)
            or any(
                not _SAFE_IDENTITY.fullmatch(case_id)
                for case_id in self.affected_case_ids
            )
            or tuple(self.case_surface_sha256) != self.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: invalid replay bundle provenance"
            )
        for hashes in self.case_surface_sha256.values():
            if set(hashes) != set(REQUIRED_E2E_SURFACES) or any(
                not _SHA256.fullmatch(value) for value in hashes.values()
            ):
                raise EvidenceContractError(
                    "REQ-G12-ARTIFACT: incomplete replay surface hashes"
                )
        if self.logical_sha256 != _logical_sha256(self.to_dict(include_hash=False)):
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: replay bundle logical hash mismatch"
            )

    def validate_for(self, work_item: IncrementalReplayWorkItem) -> None:
        self.validate()
        if (
            self.trading_date != work_item.trading_date
            or self.source_sha256 != work_item.source_sha256
            or self.work_item_sha256 != work_item.logical_sha256
            or self.affected_case_ids != work_item.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: replay bundle does not match work item"
            )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "engine_profile": self.engine_profile,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "work_item_sha256": self.work_item_sha256,
            "affected_case_ids": list(self.affected_case_ids),
            "case_surface_sha256": self.case_surface_sha256,
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class CanonicalReplayBundleStore:
    """Write and verify immutable per-date canonical surface directories."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(
        self,
        *,
        bundle: CanonicalReplayBundle,
        cases: tuple[CanonicalCaseSurfaces, ...],
    ) -> Path:
        bundle.validate()
        if tuple(case.case_id for case in cases) != bundle.affected_case_ids:
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: bundle payload case order mismatch"
            )
        target = self.root / bundle.trading_date
        temporary = self.root / f"{bundle.trading_date}.tmp"
        if target.exists() or temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: replay bundle output already exists"
            )
        temporary.mkdir(parents=True)
        for case in cases:
            if case.trading_date != bundle.trading_date:
                raise EvidenceContractError(
                    "REQ-G12-ARTIFACT: replay surface trading date mismatch"
                )
            case_directory = temporary / "cases" / case.case_id
            case_directory.mkdir(parents=True)
            for surface, payload in sorted(case.surfaces.items()):
                (case_directory / f"{surface}.json").write_bytes(payload)
        (temporary / "bundle.json").write_text(
            json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def load(
        self, trading_date: str
    ) -> tuple[CanonicalReplayBundle, tuple[CanonicalCaseSurfaces, ...]]:
        root = self.root / trading_date
        try:
            payload = json.loads((root / "bundle.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: unreadable replay bundle"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: replay bundle must be an object"
            )
        bundle = CanonicalReplayBundle.from_dict(payload)
        if bundle.trading_date != trading_date:
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: replay bundle directory/date mismatch"
            )
        cases = []
        for case_id in bundle.affected_case_ids:
            surfaces = {}
            for surface in sorted(REQUIRED_E2E_SURFACES):
                path = root / "cases" / case_id / f"{surface}.json"
                try:
                    raw = path.read_bytes()
                except OSError as error:
                    raise EvidenceContractError(
                        "REQ-G12-ARTIFACT: replay surface is unavailable"
                    ) from error
                if (
                    hashlib.sha256(raw).hexdigest()
                    != bundle.case_surface_sha256[case_id][surface]
                ):
                    raise EvidenceContractError(
                        "REQ-G12-ARTIFACT: replay surface hash mismatch"
                    )
                surfaces[surface] = raw
            cases.append(
                CanonicalCaseSurfaces(
                    case_id=case_id,
                    trading_date=trading_date,
                    surfaces=surfaces,
                )
            )
        return bundle, tuple(cases)


class ExactCanonicalDirectoryParityProcessor:
    """Compare complete canonical bundles without accepting missing surfaces."""

    profile = EXACT_CANONICAL_PARITY_PROFILE

    def __init__(self, *, reference_root: Path, candidate_root: Path) -> None:
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)

    def process(
        self,
        *,
        work_item: IncrementalReplayWorkItem,
        source: Path,
        system_directory: Path,
    ) -> IncrementalDateParityResult:
        del source, system_directory
        reference, reference_cases = self.reference_store.load(work_item.trading_date)
        candidate, candidate_cases = self.candidate_store.load(work_item.trading_date)
        reference.validate_for(work_item)
        candidate.validate_for(work_item)
        reference_by_id = {case.case_id: case for case in reference_cases}
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        cases = []
        for case_id in work_item.affected_case_ids:
            expected = reference_by_id[case_id]
            actual = candidate_by_id[case_id]
            mismatches = sum(
                expected.surfaces[surface] != actual.surfaces[surface]
                for surface in REQUIRED_E2E_SURFACES
            )
            cases.append(
                IncrementalCaseParity(
                    case_id=case_id,
                    reference_surface_sha256=expected.surface_sha256,
                    candidate_surface_sha256=actual.surface_sha256,
                    unresolved_material_count=mismatches,
                    passed=mismatches == 0,
                )
            )
        return IncrementalDateParityResult(
            processor_profile=self.profile,
            reference_artifact_sha256=reference.logical_sha256,
            candidate_artifact_sha256=candidate.logical_sha256,
            cases=tuple(cases),
        )


class PyspdReplayBundleProducer:
    """Run a prefix through PySPD and atomically export affected-case surfaces."""

    profile = PYSPD_REPLAY_PROFILE

    def __init__(
        self,
        *,
        bundle_root: Path,
        run_root: Path,
        application: PyspdApplication | None = None,
        exporter: PyspdCaseSurfaceExporter | None = None,
    ) -> None:
        self.store = CanonicalReplayBundleStore(bundle_root)
        self.run_root = run_root
        self.application = application or PyspdApplication()
        self.exporter = exporter or PyspdCaseSurfaceExporter()

    def produce(
        self,
        *,
        work_item: IncrementalReplayWorkItem,
        source: Path,
        system_directory: Path,
    ) -> CanonicalReplayBundle:
        target = self.store.root / work_item.trading_date
        if target.is_dir():
            bundle, _ = self.store.load(work_item.trading_date)
            bundle.validate_for(work_item)
            if bundle.engine_profile != self.profile:
                raise EvidenceContractError(
                    "REQ-G12-ARTIFACT: PySPD replay profile mismatch"
                )
            return bundle
        run_directory = self.run_root / work_item.trading_date
        if run_directory.exists():
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: incomplete PySPD replay run already exists"
            )
        configuration = ApplicationConfiguration(
            formulation_id=RESERVE_FORMULATION_ID,
            input_path=source,
            output_directory=run_directory,
            source_sha256=work_item.source_sha256,
            gams_system_directory=system_directory,
            solver_profile=PORTABLE_SOLVER_PROFILE,
            case_ids=work_item.case_ids,
            maximum_solve_loops=5,
            price_rounding_decimals=5,
        )
        run = self.application.run(configuration)
        exported = self.exporter.export(run, trading_date=work_item.trading_date)
        by_id = {case.case_id: case for case in exported}
        if not set(work_item.affected_case_ids).issubset(by_id):
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: PySPD replay omitted an affected case"
            )
        cases = tuple(by_id[case_id] for case_id in work_item.affected_case_ids)
        bundle = CanonicalReplayBundle.create(
            engine_profile=self.profile,
            work_item=work_item,
            cases=cases,
        )
        self.store.write(bundle=bundle, cases=cases)
        return bundle


class IncrementalReplayBundleProducer(Protocol):
    """Produce or verify one engine's canonical bundle for a work item."""

    profile: str
    store: CanonicalReplayBundleStore

    def produce(
        self,
        *,
        work_item: IncrementalReplayWorkItem,
        source: Path,
        system_directory: Path,
    ) -> CanonicalReplayBundle: ...


@dataclass(frozen=True, slots=True)
class IncrementalBundleRunSummary:
    """Progress from materializing one engine across available checkpoints."""

    available_date_count: int
    bundle_count: int
    produced_date_count: int
    affected_case_count: int
    waiting_for_trading_date: str | None
    deferred_bundle_trading_date: str | None


class IncrementalReplayBundleCoordinator:
    """Materialize one engine bundle for every currently available date."""

    def __init__(
        self,
        *,
        feed: IncrementalDiscoveryFeed,
        producer: IncrementalReplayBundleProducer,
    ) -> None:
        self.feed = feed
        self.producer = producer

    def run_available(
        self, *, maximum_new_dates: int | None = None
    ) -> IncrementalBundleRunSummary:
        if maximum_new_dates is not None and (
            isinstance(maximum_new_dates, bool) or maximum_new_dates <= 0
        ):
            raise EvidenceContractError(
                "REQ-G12-ARTIFACT: maximum new dates must be positive"
            )
        available, waiting = self.feed.scan()
        produced = 0
        affected = 0
        deferred: str | None = None
        for item in available:
            work_item = item.work_item
            affected += len(work_item.affected_case_ids)
            target = self.producer.store.root / work_item.trading_date
            existed = target.is_dir()
            if (
                not existed
                and maximum_new_dates is not None
                and produced >= maximum_new_dates
            ):
                deferred = work_item.trading_date
                break
            bundle = self.producer.produce(
                work_item=work_item,
                source=item.source,
                system_directory=self.feed.system_directory,
            )
            bundle.validate_for(work_item)
            if bundle.engine_profile != self.producer.profile:
                raise EvidenceContractError(
                    "REQ-G12-ARTIFACT: incremental producer profile mismatch"
                )
            produced += int(not existed)
        bundle_count = sum(
            (self.producer.store.root / item.work_item.trading_date).is_dir()
            for item in available
        )
        return IncrementalBundleRunSummary(
            available_date_count=len(available),
            bundle_count=bundle_count,
            produced_date_count=produced,
            affected_case_count=affected,
            waiting_for_trading_date=waiting,
            deferred_bundle_trading_date=deferred,
        )
