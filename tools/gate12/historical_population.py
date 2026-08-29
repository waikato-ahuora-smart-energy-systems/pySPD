"""Parse fail-closed affected-interval evidence from pinned vSPD v5.0.2."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from tools.gate12.evidence import EvidenceContractError

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
