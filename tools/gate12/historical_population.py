"""Parse fail-closed affected-interval evidence from pinned vSPD v5.0.2."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from tools.gate12.evidence import (
    EXPECTED_AFFECTED_INTERVALS,
    AffectedIntervalIdentity,
    AffectedIntervalManifest,
    EvidenceContractError,
)
from tools.oracle.vspd import ListingResult, VspdListingParser

MATERIAL_SHORTFALL_MW = 1e-6
HISTORICAL_EXECUTION_PROFILE = (
    "historical-v5.0.2-dailymode0-scip-solvelink5-first-loop-rtd-only-"
    "canonical-order-material-transfer"
)
HISTORICAL_COLUMNS = (
    "case_id",
    "datetime",
    "node",
    "target_node",
    "loop",
    "energy_shortfall_mw",
    "adjustment_mw",
    "model_status",
    "solver_status",
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TRADING_DATE = re.compile(r"[0-9]{8}")


@dataclass(frozen=True)
class HistoricalPatchEvidence:
    """Hash-addressed description of a forensic source overlay."""

    profile: str
    logical_sha256: str
    file_sha256: dict[str, str]


class HistoricalSourcePatcher(Protocol):
    """Apply and identify the governed historical source overlay."""

    profile: str

    def apply(self, programs: Path) -> HistoricalPatchEvidence: ...


@dataclass(frozen=True)
class HistoricalPopulationWorkspace:
    """A once-created pinned source stage and its signed patch metadata."""

    root: Path
    programs: Path
    patch_evidence: HistoricalPatchEvidence

    @classmethod
    def prepare(
        cls,
        *,
        source_tree: Path,
        root: Path,
        patcher: HistoricalSourcePatcher,
    ) -> HistoricalPopulationWorkspace:
        if root.exists():
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: enumeration workspace already exists"
            )
        if not (source_tree / "Programs").is_dir():
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: source tree lacks Programs"
            )
        root.mkdir(parents=True)
        stage = root / "vspd"
        shutil.copytree(source_tree, stage)
        programs = stage / "Programs"
        patch_evidence = patcher.apply(programs)
        unsigned = cls._unsigned_metadata(patch_evidence)
        metadata = {
            **unsigned,
            "metadata_sha256": cls._metadata_sha256(unsigned),
        }
        (root / "patch-evidence.json").write_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return cls(root=root, programs=programs, patch_evidence=patch_evidence)

    @classmethod
    def open(cls, root: Path) -> HistoricalPopulationWorkspace:
        path = root / "patch-evidence.json"
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unreadable workspace patch metadata"
            ) from error
        expected = {
            "schema_version",
            "profile",
            "logical_sha256",
            "file_sha256",
            "metadata_sha256",
        }
        if not isinstance(metadata, dict) or set(metadata) != expected:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unexpected workspace metadata schema"
            )
        unsigned = {
            key: value for key, value in metadata.items() if key != "metadata_sha256"
        }
        if metadata["metadata_sha256"] != cls._metadata_sha256(unsigned):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: workspace metadata hash mismatch"
            )
        file_hashes = metadata["file_sha256"]
        if (
            metadata["schema_version"] != 1
            or not isinstance(metadata["profile"], str)
            or not isinstance(metadata["logical_sha256"], str)
            or not _SHA256.fullmatch(metadata["logical_sha256"])
            or not isinstance(file_hashes, dict)
            or any(
                not isinstance(name, str)
                or not isinstance(value, str)
                or not _SHA256.fullmatch(value)
                for name, value in file_hashes.items()
            )
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid workspace patch metadata"
            )
        patch_evidence = HistoricalPatchEvidence(
            profile=metadata["profile"],
            logical_sha256=metadata["logical_sha256"],
            file_sha256=file_hashes,
        )
        programs = root / "vspd" / "Programs"
        for name, expected_hash in file_hashes.items():
            if Path(name).name != name:
                raise EvidenceContractError(
                    "REQ-G12-HISTORICAL: invalid patched source name"
                )
            try:
                actual_hash = hashlib.sha256((programs / name).read_bytes()).hexdigest()
            except OSError as error:
                raise EvidenceContractError(
                    "REQ-G12-HISTORICAL: patched source hash mismatch"
                ) from error
            if actual_hash != expected_hash:
                raise EvidenceContractError(
                    "REQ-G12-HISTORICAL: patched source hash mismatch"
                )
        return cls(
            root=root,
            programs=programs,
            patch_evidence=patch_evidence,
        )

    @staticmethod
    def _unsigned_metadata(evidence: HistoricalPatchEvidence) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "profile": evidence.profile,
            "logical_sha256": evidence.logical_sha256,
            "file_sha256": evidence.file_sha256,
        }

    @staticmethod
    def _metadata_sha256(values: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class HistoricalInputArtifact:
    """One Gate 1 hash-bound corrected daily input."""

    trading_date: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if not _TRADING_DATE.fullmatch(self.trading_date):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid inventory trading date"
            )
        if self.size_bytes <= 0 or not _SHA256.fullmatch(self.sha256):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid inventory size or SHA-256"
            )


@dataclass(frozen=True)
class HistoricalInputInventory:
    """Ordered set of immutable daily inputs used for enumeration."""

    artifacts: tuple[HistoricalInputArtifact, ...]

    def __post_init__(self) -> None:
        dates = [artifact.trading_date for artifact in self.artifacts]
        if not dates or len(set(dates)) != len(dates):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: inventory dates must be non-empty and unique"
            )

    @classmethod
    def load(cls, path: Path) -> HistoricalInputInventory:
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
            raw_artifacts = values["artifacts"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unreadable Gate 1 input inventory"
            ) from error
        if not isinstance(raw_artifacts, list):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: inventory artifacts must be a list"
            )
        try:
            artifacts = tuple(
                HistoricalInputArtifact(
                    trading_date=item["trading_date"],
                    size_bytes=item["size_bytes"],
                    sha256=item["sha256"],
                )
                for item in raw_artifacts
            )
        except (KeyError, TypeError) as error:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid Gate 1 inventory artifact"
            ) from error
        if values.get("artifact_count") != len(artifacts):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: Gate 1 inventory count mismatch"
            )
        return cls(artifacts)


class HistoricalPopulationShardPlanner:
    """Deterministically balance daily artifacts across isolated GAMS jobs."""

    def plan(
        self,
        inventory: HistoricalInputInventory,
        *,
        shard_count: int,
    ) -> tuple[HistoricalInputInventory, ...]:
        if (
            isinstance(shard_count, bool)
            or shard_count < 1
            or shard_count > len(inventory.artifacts)
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid population shard count"
            )
        bins: list[list[HistoricalInputArtifact]] = [[] for _ in range(shard_count)]
        totals = [0] * shard_count
        for artifact in sorted(
            inventory.artifacts,
            key=lambda item: (-item.size_bytes, item.trading_date),
        ):
            index = min(range(shard_count), key=lambda item: (totals[item], item))
            bins[index].append(artifact)
            totals[index] += artifact.size_bytes
        return tuple(
            HistoricalInputInventory(
                tuple(sorted(items, key=lambda item: item.trading_date))
            )
            for items in bins
        )


@dataclass(frozen=True)
class HistoricalGdxCaseIndex:
    """Selected case identities and their source trading-period mapping."""

    cases: tuple[tuple[str, str], ...]
    trading_periods: dict[tuple[str, str], str]

    def __post_init__(self) -> None:
        if not self.cases or len(set(self.cases)) != len(self.cases):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: GDX cases must be non-empty and unique"
            )
        if set(self.cases) != set(self.trading_periods):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: incomplete GDX trading-period map"
            )


class HistoricalCaseIndexLoader(Protocol):
    """Load the exact case/period selection surface of a daily GDX."""

    def load(self, path: Path, system_directory: Path) -> HistoricalGdxCaseIndex: ...


class GamsTransferCaseIndexLoader:
    """Read the canonical mappings and select the disclosed RTD modes only."""

    def load(self, path: Path, system_directory: Path) -> HistoricalGdxCaseIndex:
        from gams.transfer import Container

        container = Container(system_directory=str(system_directory))
        container.read(str(path), symbols=["i_dateTimeTradePeriodMap", "i_runMode"])
        records = container["i_dateTimeTradePeriodMap"].records
        run_mode_records = container["i_runMode"].records
        if records is None or run_mode_records is None:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: missing GDX case-selection mapping"
            )
        periods = {
            (str(row.ca), str(row.dt)): str(row.tp)
            for row in records.itertuples(index=False)
        }
        study_mode = {
            str(row.ca): int(float(row.value))
            for row in run_mode_records.itertuples(index=False)
            if str(row.casePar) == "studyMode"
        }
        return self.select_rtd(periods=periods, study_mode=study_mode)

    @staticmethod
    def select_rtd(
        *,
        periods: dict[tuple[str, str], str],
        study_mode: dict[str, int],
    ) -> HistoricalGdxCaseIndex:
        selected = {
            key: trading_period
            for key, trading_period in periods.items()
            if study_mode.get(key[0]) in {101, 201}
        }
        return HistoricalGdxCaseIndex(cases=tuple(selected), trading_periods=selected)


class HistoricalGamsExecutor(Protocol):
    """Execute one GAMS compilation or run step."""

    def execute(
        self, executable: Path, programs: Path, arguments: tuple[str, ...]
    ) -> None: ...


class SubprocessHistoricalGamsExecutor:
    """Run GAMS without treating process exit alone as solve evidence."""

    _NETWORK_LICENCE_START = "Error when trying to start network session"
    _NETWORK_LICENCE_REASONS = (
        "server for licensing",
        '"reason":"node_limit"',
    )

    def __init__(
        self,
        *,
        network_license_attempts: int = 1,
        network_license_retry_seconds: float = 300.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            not isinstance(network_license_attempts, int)
            or isinstance(network_license_attempts, bool)
            or network_license_attempts < 1
            or not math.isfinite(network_license_retry_seconds)
            or network_license_retry_seconds < 0.0
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid GAMS network-licence retry policy"
            )
        self.network_license_attempts = network_license_attempts
        self.network_license_retry_seconds = network_license_retry_seconds
        self.sleeper = sleeper

    def execute(
        self, executable: Path, programs: Path, arguments: tuple[str, ...]
    ) -> None:
        log_path = programs / Path(arguments[0]).with_suffix(".log").name
        for attempt in range(1, self.network_license_attempts + 1):
            previous_log_signature = self._file_signature(log_path)
            completed = subprocess.run(
                [str(executable), *arguments],
                cwd=programs,
                check=False,
            )
            if completed.returncode == 0:
                return
            transient = self._is_new_network_licence_failure(
                log_path, previous_log_signature
            )
            if transient and attempt < self.network_license_attempts:
                self.sleeper(self.network_license_retry_seconds)
                continue
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: GAMS process did not complete"
            )

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _is_new_network_licence_failure(
        self,
        log_path: Path,
        previous_signature: tuple[int, int] | None,
    ) -> bool:
        if self._file_signature(log_path) == previous_signature:
            return False
        try:
            text = log_path.read_text(errors="replace")
        except OSError:
            return False
        return self._NETWORK_LICENCE_START in text and any(
            marker in text for marker in self._NETWORK_LICENCE_REASONS
        )


class HistoricalVspdSourcePatcher:
    """Apply the minimal, fail-closed v5.0.2 population-discovery overlay."""

    profile = "historical-v5.0.2-dailymode0-scip-first-loop-material-transfer"

    def apply(self, programs: Path) -> HistoricalPatchEvidence:
        settings = programs / "vSPDsettings.inc"
        period = programs / "vSPDperiod.gms"
        solve = programs / "vSPDsolve.gms"
        for path in (settings, period, solve):
            if not path.is_file():
                raise EvidenceContractError(
                    f"REQ-G12-HISTORICAL: missing pinned source file: {path.name}"
                )

        settings_text = settings.read_text(encoding="utf-8")
        settings_text = self._replace(
            settings_text,
            "'%system.fp%..\\Input\\'",
            "'%system.fp%../Input/'",
        )
        settings_text = self._replace(
            settings_text,
            "'%system.fp%..\\Output\\'",
            "'%system.fp%../Output/'",
        )
        settings_text = self._replace(
            settings_text,
            "'%system.fp%..\\Override\\'",
            "'%system.fp%../Override/'",
        )
        settings_text = self._replace(
            settings_text,
            "$setglobal Solver                          Cplex",
            "$setglobal Solver                          SCIP",
        )
        settings_text = self._replace(
            settings_text,
            "Scalar dailymode                         / 1 / ;",
            "Scalar dailymode                         / 0 / ;",
        )

        period_text = period.read_text(encoding="utf-8")
        period_text = self._replace_all(
            period_text, "%inputPath%\\%GDXname%.gdx", "%inputPath%/%GDXname%.gdx", 2
        )
        period_text = self._replace(
            period_text,
            "%programPath%\\vSPDperiod.gdx",
            "%programPath%/vSPDperiod.gdx",
        )

        solve_text = solve.read_text(encoding="utf-8")
        solve_text = self._replace(
            solve_text, "option lp = %Solver% ;", "option lp = HiGHS ;"
        )
        solve_text = self._replace(
            solve_text,
            "option mip = %Solver% ;",
            "option rmip = HiGHS ;\noption mip = SCIP ;",
        )
        solve_text = self._replace_all(
            solve_text, ".Optfile = 1 ;", ".Optfile = 0 ;", 3
        )
        solve_text = self._replace_all(
            solve_text, "%inputPath%\\%GDXname%.gdx", "%inputPath%/%GDXname%.gdx", 4
        )
        solve_text = self._sub(
            solve_text,
            r'^(File rep "Write to a report"[^\n]*;)$',
            r"\1\n\n"
            'File gate12 "Gate 12 historical shortfall evidence" '
            '/"gate12_%GDXname%_shortfall.txt"/;\n'
            "gate12.lw = 0; gate12.ap = 0; gate12.nd = 12;\n"
            "putclose gate12 'case_id|datetime|node|target_node|loop|energy_shortfall_mw|"
            "adjustment_mw|model_status|solver_status' /;\n"
            "gate12.ap = 1;",
        )
        solve_text = self._sub(
            solve_text,
            r"^(PotentialModellingInconsistency\(ca,dt,n\)\s*=\s*1\s*\$[^\n]*;)$",
            r"\1\nmaxSolveLoops(ca,dt) $ case2dt(ca,dt) = 1.5;",
        )
        solve_text = self._replace(
            solve_text,
            "loop( (t,n) $ EnergyShortfallMW(t,n),",
            "loop( (t,n) $ (abs(EnergyShortfallMW(t,n)) > 0.000001),",
        )
        solve_text = self._sub(
            solve_text,
            r"^(\s*loop\( nodeTonode\(t,n,n1\) \$ ShortfallTransferFromTo\(t,n,n1\),\n"
            r"\s*putclose rep [^\n]*;\n\s*\) ;[^\n]*)$",
            r"\1\n\n"
            "            loop( nodeTonode(t,n,n1)\n"
            "                $ { ShortfallTransferFromTo(t,n,n1)\n"
            "                and (abs(EnergyShortfallMW(t,n)) > 0.000001) },\n"
            "               putclose gate12 ca.tl:0 '|' dt.tl:0 '|' n.tl:0 '|' n1.tl:0 '|'\n"
            "                   LoopCount(ca,dt):0:0 '|' EnergyShortfallMW(t,n):0:12 '|'\n"
            "                   ShortfallAdjustmentMW(t,n):0:12 '|' vSPD_NMIR.modelstat:0:0 '|'\n"
            "                   vSPD_NMIR.solvestat:0:0 /;\n"
            "            ) ;",
        )

        settings.write_text(settings_text, encoding="utf-8")
        period.write_text(period_text, encoding="utf-8")
        solve.write_text(solve_text, encoding="utf-8")
        hashes = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (settings, period, solve)
        }
        logical = hashlib.sha256(
            json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return HistoricalPatchEvidence(self.profile, logical, hashes)

    @staticmethod
    def _replace(text: str, old: str, new: str) -> str:
        return HistoricalVspdSourcePatcher._replace_all(text, old, new, 1)

    @staticmethod
    def _replace_all(text: str, old: str, new: str, expected: int) -> str:
        count = text.count(old)
        if count != expected:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: pinned source drift "
                f"for {old!r}; expected {expected}, found {count}"
            )
        return text.replace(old, new)

    @staticmethod
    def _sub(text: str, pattern: str, replacement: str) -> str:
        result, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
        if count != 1:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: pinned source drift "
                f"for pattern {pattern!r}; expected 1, found {count}"
            )
        return result


@dataclass(frozen=True)
class HistoricalShortfallRecord:
    """One node-level v5.0.2 shortfall-removal decision."""

    case_id: str
    date_time: str
    node: str
    target_node: str
    solve_loop: int
    energy_shortfall_mw: float
    adjustment_mw: float
    model_status: int
    solver_status: int

    @property
    def case_key(self) -> tuple[str, str]:
        return (self.case_id, self.date_time)


@dataclass(frozen=True)
class HistoricalShortfallEvidence:
    """Validated node records emitted by one pinned historical daily run."""

    source_name: str
    records: tuple[HistoricalShortfallRecord, ...]

    @classmethod
    def parse(cls, text: str, *, source_name: str) -> HistoricalShortfallEvidence:
        if not source_name.strip():
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: source name must not be empty"
            )
        reader = csv.DictReader(io.StringIO(text), delimiter="|")
        if tuple(reader.fieldnames or ()) != HISTORICAL_COLUMNS:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unexpected evidence schema"
            )
        records = tuple(cls._record(row) for row in reader)
        if len(set(records)) != len(records):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: duplicate node evidence row"
            )
        return cls(source_name=source_name, records=records)

    @staticmethod
    def _record(row: dict[str, str]) -> HistoricalShortfallRecord:
        required_text = (
            row["case_id"],
            row["datetime"],
            row["node"],
            row["target_node"],
        )
        if any(not value.strip() for value in required_text):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: identity fields must not be empty"
            )
        try:
            solve_loop = int(row["loop"])
            energy = float(row["energy_shortfall_mw"])
            adjustment = float(row["adjustment_mw"])
            model_status = int(row["model_status"])
            solver_status = int(row["solver_status"])
        except (TypeError, ValueError) as error:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: evidence values must be numeric"
            ) from error
        if not math.isfinite(energy) or not math.isfinite(adjustment):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: evidence values must be finite"
            )
        if solve_loop != 1:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: discovery must use the first solve loop"
            )
        if energy <= MATERIAL_SHORTFALL_MW:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: expected a material shortfall transfer"
            )
        if adjustment < energy:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: adjustment cannot be below shortfall"
            )
        if model_status != 1 or solver_status != 1:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: evidence requires an optimal solve"
            )
        return HistoricalShortfallRecord(
            case_id=row["case_id"],
            date_time=row["datetime"],
            node=row["node"],
            target_node=row["target_node"],
            solve_loop=solve_loop,
            energy_shortfall_mw=energy,
            adjustment_mw=adjustment,
            model_status=model_status,
            solver_status=solver_status,
        )

    @property
    def affected_cases(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted({record.case_key for record in self.records}))


@dataclass(frozen=True)
class HistoricalPopulationCheckpoint:
    """One complete, reusable historical daily-enumeration result."""

    trading_date: str
    source_sha256: str
    patch_sha256: str
    solver_profile: str
    selected_case_count: int
    solved_case_count: int
    all_solves_optimal: bool
    artifact_sha256: dict[str, str]
    evidence: HistoricalShortfallEvidence
    logical_sha256: str

    @classmethod
    def create(
        cls,
        *,
        trading_date: str,
        source_sha256: str,
        patch_sha256: str,
        solver_profile: str,
        selected_case_count: int,
        solved_case_count: int,
        all_solves_optimal: bool,
        artifact_sha256: dict[str, str],
        evidence: HistoricalShortfallEvidence,
    ) -> HistoricalPopulationCheckpoint:
        cls._validate(
            trading_date=trading_date,
            source_sha256=source_sha256,
            patch_sha256=patch_sha256,
            solver_profile=solver_profile,
            selected_case_count=selected_case_count,
            solved_case_count=solved_case_count,
            all_solves_optimal=all_solves_optimal,
            artifact_sha256=artifact_sha256,
            evidence=evidence,
        )
        values: dict[str, Any] = {
            "schema_version": 1,
            "trading_date": trading_date,
            "source_sha256": source_sha256,
            "patch_sha256": patch_sha256,
            "solver_profile": solver_profile,
            "selected_case_count": selected_case_count,
            "solved_case_count": solved_case_count,
            "all_solves_optimal": all_solves_optimal,
            "artifact_sha256": artifact_sha256,
            "evidence": cls._evidence_dict(evidence),
        }
        logical_sha256 = cls._logical_sha256(values)
        return cls(
            trading_date=trading_date,
            source_sha256=source_sha256,
            patch_sha256=patch_sha256,
            solver_profile=solver_profile,
            selected_case_count=selected_case_count,
            solved_case_count=solved_case_count,
            all_solves_optimal=all_solves_optimal,
            artifact_sha256=artifact_sha256,
            evidence=evidence,
            logical_sha256=logical_sha256,
        )

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> HistoricalPopulationCheckpoint:
        expected = {
            "schema_version",
            "trading_date",
            "source_sha256",
            "patch_sha256",
            "solver_profile",
            "selected_case_count",
            "solved_case_count",
            "all_solves_optimal",
            "artifact_sha256",
            "evidence",
            "logical_sha256",
        }
        if set(values) != expected or values.get("schema_version") != 1:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unexpected checkpoint schema"
            )
        unsigned = {
            key: value for key, value in values.items() if key != "logical_sha256"
        }
        if values["logical_sha256"] != cls._logical_sha256(unsigned):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: checkpoint logical hash mismatch"
            )
        evidence_values = values["evidence"]
        if not isinstance(evidence_values, dict):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unexpected checkpoint evidence"
            )
        evidence = cls._evidence_from_dict(evidence_values)
        try:
            checkpoint = cls.create(
                trading_date=values["trading_date"],
                source_sha256=values["source_sha256"],
                patch_sha256=values["patch_sha256"],
                solver_profile=values["solver_profile"],
                selected_case_count=values["selected_case_count"],
                solved_case_count=values["solved_case_count"],
                all_solves_optimal=values["all_solves_optimal"],
                artifact_sha256=values["artifact_sha256"],
                evidence=evidence,
            )
        except (TypeError, ValueError) as error:
            if isinstance(error, EvidenceContractError):
                raise
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid checkpoint values"
            ) from error
        if values["logical_sha256"] != checkpoint.logical_sha256:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: checkpoint logical hash mismatch"
            )
        return checkpoint

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "patch_sha256": self.patch_sha256,
            "solver_profile": self.solver_profile,
            "selected_case_count": self.selected_case_count,
            "solved_case_count": self.solved_case_count,
            "all_solves_optimal": self.all_solves_optimal,
            "artifact_sha256": self.artifact_sha256,
            "evidence": self._evidence_dict(self.evidence),
            "logical_sha256": self.logical_sha256,
        }

    @property
    def affected_case_count(self) -> int:
        return len(self.evidence.affected_cases)

    @staticmethod
    def _validate(
        *,
        trading_date: str,
        source_sha256: str,
        patch_sha256: str,
        solver_profile: str,
        selected_case_count: int,
        solved_case_count: int,
        all_solves_optimal: bool,
        artifact_sha256: dict[str, str],
        evidence: HistoricalShortfallEvidence,
    ) -> None:
        if not isinstance(trading_date, str) or not _TRADING_DATE.fullmatch(
            trading_date
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid YYYYMMDD trading date"
            )
        if not all(
            isinstance(value, str) and _SHA256.fullmatch(value)
            for value in (source_sha256, patch_sha256)
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: source and patch require SHA-256 values"
            )
        if not isinstance(solver_profile, str) or not solver_profile.strip():
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: solver profile must not be empty"
            )
        if (
            not isinstance(selected_case_count, int)
            or isinstance(selected_case_count, bool)
            or selected_case_count <= 0
            or solved_case_count != selected_case_count
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: every selected case must have a solve"
            )
        if all_solves_optimal is not True:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: every daily solve must be optimal"
            )
        if set(artifact_sha256) != {"progress", "listing", "evidence"} or any(
            not isinstance(value, str) or not _SHA256.fullmatch(value)
            for value in artifact_sha256.values()
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: raw completion artifacts require SHA-256 values"
            )
        if evidence.source_name != f"Pricing_{trading_date}":
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: evidence source does not match trading date"
            )

    @staticmethod
    def _evidence_dict(evidence: HistoricalShortfallEvidence) -> dict[str, Any]:
        return {
            "source_name": evidence.source_name,
            "records": [asdict(record) for record in evidence.records],
        }

    @staticmethod
    def _evidence_from_dict(values: dict[str, Any]) -> HistoricalShortfallEvidence:
        if set(values) != {"source_name", "records"} or not isinstance(
            values["records"], list
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unexpected checkpoint evidence schema"
            )
        lines = ["|".join(HISTORICAL_COLUMNS)]
        for record in values["records"]:
            if not isinstance(record, dict):
                raise EvidenceContractError(
                    "REQ-G12-HISTORICAL: unexpected checkpoint evidence record"
                )
            try:
                lines.append(
                    "|".join(
                        str(record[name])
                        for name in (
                            "case_id",
                            "date_time",
                            "node",
                            "target_node",
                            "solve_loop",
                            "energy_shortfall_mw",
                            "adjustment_mw",
                            "model_status",
                            "solver_status",
                        )
                    )
                )
            except KeyError as error:
                raise EvidenceContractError(
                    "REQ-G12-HISTORICAL: unexpected checkpoint evidence record"
                ) from error
        source_name = values["source_name"]
        if not isinstance(source_name, str):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid checkpoint evidence source"
            )
        return HistoricalShortfallEvidence.parse(
            "\n".join(lines) + "\n", source_name=source_name
        )

    @staticmethod
    def _logical_sha256(values: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class HistoricalPopulationCheckpointStore:
    """Atomically persist and qualify resumable daily checkpoints."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, checkpoint: HistoricalPopulationCheckpoint) -> Path:
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

    def load(self, trading_date: str) -> HistoricalPopulationCheckpoint | None:
        path = self._path(trading_date)
        if not path.is_file():
            return None
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unreadable population checkpoint"
            ) from error
        if not isinstance(values, dict):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: checkpoint must be a JSON object"
            )
        return HistoricalPopulationCheckpoint.from_dict(values)

    def reusable(
        self,
        trading_date: str,
        *,
        source_sha256: str,
        patch_sha256: str,
        solver_profile: str,
    ) -> bool:
        checkpoint = self.load(trading_date)
        return bool(
            checkpoint is not None
            and checkpoint.source_sha256 == source_sha256
            and checkpoint.patch_sha256 == patch_sha256
            and checkpoint.solver_profile == solver_profile
            and checkpoint.solved_case_count == checkpoint.selected_case_count
            and checkpoint.all_solves_optimal
        )

    def _path(self, trading_date: str) -> Path:
        if not _TRADING_DATE.fullmatch(trading_date):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid YYYYMMDD trading date"
            )
        return self.root / f"{trading_date}.json"


class HistoricalDailyCompletionValidator:
    """Bind exact progress, listing, and node evidence for one complete day."""

    _success = re.compile(
        r"^The caseID: (?P<case>[A-Za-z0-9_.-]+) "
        r"\((?P<datetime>[^\n]+)\) is 1st solved successfully\.$",
        re.MULTILINE,
    )

    def validate(
        self,
        *,
        trading_date: str,
        source_sha256: str,
        patch_sha256: str,
        solver_profile: str,
        selected_cases: tuple[tuple[str, str], ...],
        progress_text: str,
        listing: ListingResult,
        listing_text: str,
        evidence_text: str,
    ) -> HistoricalPopulationCheckpoint:
        selected = set(selected_cases)
        successful = tuple(
            (match.group("case"), match.group("datetime"))
            for match in self._success.finditer(progress_text)
        )
        exact_progress = bool(
            selected_cases
            and len(selected) == len(selected_cases)
            and len(successful) == len(selected_cases)
            and successful == selected_cases
        )
        exact_listing = bool(
            listing.all_optimal
            and len(listing.primary) == len(selected_cases)
            and not listing.pricing
            and all(record.solver == "SCIP" for record in listing.operational_records)
        )
        if not exact_progress or not exact_listing:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: daily completion is not exact and optimal"
            )
        evidence = HistoricalShortfallEvidence.parse(
            evidence_text, source_name=f"Pricing_{trading_date}"
        )
        if not set(evidence.affected_cases).issubset(selected):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: daily completion contains unselected evidence"
            )
        return HistoricalPopulationCheckpoint.create(
            trading_date=trading_date,
            source_sha256=source_sha256,
            patch_sha256=patch_sha256,
            solver_profile=solver_profile,
            selected_case_count=len(selected_cases),
            solved_case_count=len(successful),
            all_solves_optimal=True,
            artifact_sha256={
                "progress": hashlib.sha256(progress_text.encode()).hexdigest(),
                "listing": hashlib.sha256(listing_text.encode()).hexdigest(),
                "evidence": hashlib.sha256(evidence_text.encode()).hexdigest(),
            },
            evidence=evidence,
        )


class HistoricalAffectedManifestBuilder:
    """Promote complete daily evidence into the immutable 546-case manifest."""

    def build(
        self,
        *,
        checkpoints: tuple[HistoricalPopulationCheckpoint, ...],
        inventory: HistoricalInputInventory,
        case_indices: dict[str, HistoricalGdxCaseIndex],
        source_release: str,
        reference_commit: str,
    ) -> AffectedIntervalManifest:
        by_date = {checkpoint.trading_date: checkpoint for checkpoint in checkpoints}
        source_hashes = {
            artifact.trading_date: artifact.sha256 for artifact in inventory.artifacts
        }
        if (
            len(by_date) != len(checkpoints)
            or set(by_date) != set(source_hashes)
            or set(case_indices) != set(source_hashes)
        ):
            raise EvidenceContractError(
                "REQ-G12-POPULATION: daily evidence does not match the inventory"
            )
        identities: list[AffectedIntervalIdentity] = []
        for artifact in inventory.artifacts:
            checkpoint = by_date[artifact.trading_date]
            if checkpoint.source_sha256 != artifact.sha256:
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: checkpoint source hash mismatch"
                )
            index = case_indices[artifact.trading_date]
            records_by_case: dict[tuple[str, str], list[HistoricalShortfallRecord]] = {}
            for record in checkpoint.evidence.records:
                records_by_case.setdefault(record.case_key, []).append(record)
            for case_key in sorted(records_by_case):
                trading_period = index.trading_periods.get(case_key)
                if trading_period is None:
                    raise EvidenceContractError(
                        "REQ-G12-POPULATION: affected case lacks a trading period"
                    )
                node_evidence = ",".join(
                    f"{record.node}->{record.target_node}={record.adjustment_mw:.12g}MW"
                    for record in sorted(
                        records_by_case[case_key],
                        key=lambda value: (value.node, value.target_node),
                    )
                )
                identities.append(
                    AffectedIntervalIdentity(
                        case_id=case_key[0],
                        date_time=case_key[1],
                        trading_period=trading_period,
                        trading_date=artifact.trading_date,
                        source_sha256=artifact.sha256,
                        discovery_rationale=(
                            "pinned-v5.0.2 non-daily optimal SCIP first-loop material "
                            f"shortfall transfers: {node_evidence}"
                        ),
                    )
                )
        manifest = AffectedIntervalManifest(
            source_release=source_release,
            reference_commit=reference_commit,
            identities=tuple(identities),
        )
        manifest.validate(expected_source_hashes=source_hashes)
        return manifest


class HistoricalPopulationRunner:
    """Enumerate every hash-bound day with exact, resumable evidence."""

    def __init__(
        self,
        *,
        programs: Path,
        input_root: Path,
        inventory: HistoricalInputInventory,
        system_directory: Path,
        gams_executable: Path,
        patch_evidence: HistoricalPatchEvidence,
        checkpoint_store: HistoricalPopulationCheckpointStore,
        index_loader: HistoricalCaseIndexLoader | None = None,
        executor: HistoricalGamsExecutor | None = None,
        listing_parser: VspdListingParser | None = None,
        completion_validator: HistoricalDailyCompletionValidator | None = None,
    ) -> None:
        self.programs = programs
        self.input_root = input_root
        self.inventory = inventory
        self.system_directory = system_directory
        self.gams_executable = gams_executable
        self.patch_evidence = patch_evidence
        self.checkpoint_store = checkpoint_store
        self.index_loader = index_loader or GamsTransferCaseIndexLoader()
        self.executor = executor or SubprocessHistoricalGamsExecutor()
        self.listing_parser = listing_parser or VspdListingParser()
        self.completion_validator = (
            completion_validator or HistoricalDailyCompletionValidator()
        )

    def run(self) -> tuple[HistoricalPopulationCheckpoint, ...]:
        self._validate_patch()
        sources = {
            artifact.trading_date: self._validated_source(artifact)
            for artifact in self.inventory.artifacts
        }
        pending = tuple(
            artifact
            for artifact in self.inventory.artifacts
            if not self.checkpoint_store.reusable(
                artifact.trading_date,
                source_sha256=artifact.sha256,
                patch_sha256=self.patch_evidence.logical_sha256,
                solver_profile=HISTORICAL_EXECUTION_PROFILE,
            )
        )
        retained = tuple(
            checkpoint
            for artifact in self.inventory.artifacts
            if (checkpoint := self.checkpoint_store.load(artifact.trading_date))
            is not None
            and self.checkpoint_store.reusable(
                artifact.trading_date,
                source_sha256=artifact.sha256,
                patch_sha256=self.patch_evidence.logical_sha256,
                solver_profile=HISTORICAL_EXECUTION_PROFILE,
            )
        )
        affected_count = sum(item.affected_case_count for item in retained)
        self._validate_affected_count(affected_count)
        if pending:
            self.executor.execute(
                self.gams_executable,
                self.programs,
                ("vSPDmodel.gms", "s=vSPDmodel", "lo=2"),
            )
        for artifact in pending:
            checkpoint = self._run_day(artifact, sources[artifact.trading_date])
            affected_count += checkpoint.affected_case_count
            self._validate_affected_count(affected_count)
            self.checkpoint_store.write(checkpoint)
        results = tuple(
            self.checkpoint_store.load(artifact.trading_date)
            for artifact in self.inventory.artifacts
        )
        if any(checkpoint is None for checkpoint in results):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: enumeration left an incomplete checkpoint set"
            )
        return tuple(checkpoint for checkpoint in results if checkpoint is not None)

    @staticmethod
    def _validate_affected_count(affected_count: int) -> None:
        if affected_count > EXPECTED_AFFECTED_INTERVALS:
            raise EvidenceContractError(
                "REQ-G12-POPULATION: enumeration exceeded the declared "
                f"{EXPECTED_AFFECTED_INTERVALS}-case population"
            )

    def _run_day(
        self, artifact: HistoricalInputArtifact, source: Path
    ) -> HistoricalPopulationCheckpoint:
        index = self.index_loader.load(source, self.system_directory)
        self._stage_day(artifact, source, selected_cases=index.cases)
        self.executor.execute(
            self.gams_executable,
            self.programs,
            ("vSPDperiod.gms", "lo=2"),
        )
        self.executor.execute(
            self.gams_executable,
            self.programs,
            (
                "vSPDsolve.gms",
                "r=vSPDmodel",
                "lo=2",
                "ide=1",
                "Errmsg=1",
                "holdFixed=0",
                "solvelink=5",
            ),
        )
        listing_text = (self.programs / "vSPDsolve.lst").read_text(errors="replace")
        listing = self.listing_parser.parse_text(listing_text)
        evidence_path = (
            self.programs / f"gate12_Pricing_{artifact.trading_date}_shortfall.txt"
        )
        return self.completion_validator.validate(
            trading_date=artifact.trading_date,
            source_sha256=artifact.sha256,
            patch_sha256=self.patch_evidence.logical_sha256,
            solver_profile=HISTORICAL_EXECUTION_PROFILE,
            selected_cases=index.cases,
            progress_text=(self.programs / "ProgressReport.txt").read_text(
                encoding="utf-8"
            ),
            listing=listing,
            listing_text=listing_text,
            evidence_text=evidence_path.read_text(encoding="utf-8"),
        )

    def _stage_day(
        self,
        artifact: HistoricalInputArtifact,
        source: Path,
        *,
        selected_cases: tuple[tuple[str, str], ...],
    ) -> None:
        input_directory = self.programs.parent / "Input"
        input_directory.mkdir(parents=True, exist_ok=True)
        staged_input = input_directory / f"Pricing_{artifact.trading_date}.gdx"
        if staged_input.exists() or staged_input.is_symlink():
            staged_input.unlink()
        staged_input.symlink_to(source)
        (self.programs / "vSPDcase.inc").write_text(
            f"$setglobal GDXname Pricing_{artifact.trading_date}\n",
            encoding="utf-8",
        )
        case_ids = tuple(dict.fromkeys(case_id for case_id, _ in selected_cases))
        if not case_ids or any(
            not re.fullmatch(r"[A-Za-z0-9_]+", case_id) for case_id in case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid exact case selection"
            )
        (self.programs / "vSPDtpsToSolve.inc").write_text(
            "/\n" + "\n".join(case_ids) + "\n/\n", encoding="utf-8"
        )
        for path in (
            self.programs / "ProgressReport.txt",
            self.programs / "vSPDsolve.lst",
            self.programs / f"gate12_Pricing_{artifact.trading_date}_shortfall.txt",
        ):
            path.unlink(missing_ok=True)

    def _validated_source(self, artifact: HistoricalInputArtifact) -> Path:
        path = (
            self.input_root
            / artifact.trading_date[:4]
            / f"Pricing_{artifact.trading_date}.gdx"
        )
        if (
            not path.is_file()
            or path.stat().st_size != artifact.size_bytes
            or self._sha256(path) != artifact.sha256
        ):
            raise EvidenceContractError(
                f"REQ-G12-HISTORICAL: source hash mismatch for {artifact.trading_date}"
            )
        return path.resolve()

    def _validate_patch(self) -> None:
        if (
            not _SHA256.fullmatch(self.patch_evidence.logical_sha256)
            or not self.patch_evidence.profile.strip()
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid patch evidence identity"
            )
        for name, expected in self.patch_evidence.file_sha256.items():
            path = self.programs / name
            if (
                not _SHA256.fullmatch(expected)
                or not path.is_file()
                or self._sha256(path) != expected
            ):
                raise EvidenceContractError(
                    f"REQ-G12-HISTORICAL: patch hash mismatch for {name}"
                )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
