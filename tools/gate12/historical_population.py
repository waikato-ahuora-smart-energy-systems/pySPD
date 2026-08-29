"""Parse fail-closed affected-interval evidence from pinned vSPD v5.0.2."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass

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
