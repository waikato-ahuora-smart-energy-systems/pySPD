"""Parse fail-closed affected-interval evidence from pinned vSPD v5.0.2."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools.gate12.evidence import EvidenceContractError
from tools.oracle.vspd import ListingResult

MATERIAL_SHORTFALL_MW = 1e-6
HISTORICAL_COLUMNS = (
    "case_id",
    "datetime",
    "node",
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


class HistoricalVspdSourcePatcher:
    """Apply the minimal, fail-closed v5.0.2 population-discovery overlay."""

    profile = "historical-v5.0.2-scip-first-loop"

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
            "Scalar dailymode                         / 1 / ;",
            "Scalar dailymode                         / 0 / ;",
        )
        settings_text = self._replace(
            settings_text,
            "$setglobal Solver                          Cplex",
            "$setglobal Solver                          SCIP",
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
            solve_text, "%inputPath%\\%GDXname%.gdx", "%inputPath%/%GDXname%.gdx", 3
        )
        solve_text = self._sub(
            solve_text,
            r'^(File rep "Write to a report"[^\n]*;)$',
            r"\1\n\n"
            'File gate12 "Gate 12 historical shortfall evidence" '
            '/"gate12_%GDXname%_shortfall.txt"/;\n'
            "gate12.lw = 0; gate12.ap = 0; gate12.nd = 12;\n"
            "putclose gate12 'case_id|datetime|node|loop|energy_shortfall_mw|"
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
            "EnergyShortfallMW(t,n) > 0",
            "EnergyShortfallMW(t,n) > 0.000001",
        )
        solve_text = self._sub(
            solve_text,
            r"^(\s*ShortfallAdjustmentMW\(t,n\)\s*\$\s*EligibleShortfallRemoval\(t,n\)[^\n]*;)$",
            r"\1\n\n"
            "        loop( (t,n) $ EligibleShortfallRemoval(t,n),\n"
            "            putclose gate12 ca.tl:0 '|' dt.tl:0 '|' n.tl:0 '|'\n"
            "                LoopCount(ca,dt):0:0 '|' EnergyShortfallMW(t,n):0:12 '|'\n"
            "                ShortfallAdjustmentMW(t,n):0:12 '|' vSPD_NMIR.modelstat:0:0 '|'\n"
            "                vSPD_NMIR.solvestat:0:0 /;\n"
            "        ) ;",
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
        required_text = (row["case_id"], row["datetime"], row["node"])
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
                "REQ-G12-HISTORICAL: expected a material shortfall"
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
            "evidence",
            "logical_sha256",
        }
        if set(values) != expected or values.get("schema_version") != 1:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: unexpected checkpoint schema"
            )
        unsigned = {key: value for key, value in values.items() if key != "logical_sha256"}
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
            json.dumps(
                checkpoint.to_dict(), sort_keys=True, separators=(",", ":")
            )
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
            and set(successful) == selected
        )
        exact_listing = bool(
            listing.all_optimal
            and len(listing.primary) == len(selected_cases)
            and not listing.pricing
            and all(
                record.solver == "SCIP" for record in listing.operational_records
            )
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
            evidence=evidence,
        )
