"""Canonical PySPD case-surface export for Gate 12 E2E comparison."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from pyspd.application import ApplicationRun
from pyspd.reporting import ReportBundle, ReportError
from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError

_TRADING_DATE = re.compile(r"[0-9]{8}")


@dataclass(frozen=True, slots=True)
class CanonicalCaseSurfaces:
    """Exact canonical bytes for every required surface of one PySPD case."""

    case_id: str
    trading_date: str
    surfaces: Mapping[str, bytes]

    def __post_init__(self) -> None:
        normalized = dict(self.surfaces)
        if (
            not self.case_id.strip()
            or not _TRADING_DATE.fullmatch(self.trading_date)
            or set(normalized) != set(REQUIRED_E2E_SURFACES)
            or any(not isinstance(payload, bytes) for payload in normalized.values())
        ):
            raise EvidenceContractError(
                "REQ-G12-PYSPD-SURFACE: incomplete canonical case surfaces"
            )
        object.__setattr__(self, "surfaces", MappingProxyType(normalized))

    @property
    def surface_sha256(self) -> dict[str, str]:
        return {
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in sorted(self.surfaces.items())
        }


class PyspdCaseSurfaceExporter:
    """Project a completed application run onto the twelve Gate 12 surfaces."""

    def export(
        self, run: ApplicationRun, *, trading_date: str
    ) -> tuple[CanonicalCaseSurfaces, ...]:
        result = run.result
        if result.published is None:
            raise EvidenceContractError(
                "REQ-G12-PYSPD-SURFACE: daily run has no published output"
            )
        try:
            reports = ReportBundle.read(run.output_directory)
        except (OSError, ReportError, ValueError, KeyError) as error:
            raise EvidenceContractError(
                "REQ-G12-PYSPD-SURFACE: report evidence is unreadable"
            ) from error
        exported = tuple(
            self._case_surfaces(run, case, reports, trading_date=trading_date)
            for case in result.cases
        )
        case_ids = [item.case_id for item in exported]
        if len(case_ids) != len(set(case_ids)):
            raise EvidenceContractError(
                "REQ-G12-PYSPD-SURFACE: duplicate completed case identity"
            )
        return exported

    def _case_surfaces(
        self,
        run: ApplicationRun,
        case: Any,
        reports: ReportBundle,
        *,
        trading_date: str,
    ) -> CanonicalCaseSurfaces:
        accepted = case.accepted
        prices = case.prices
        published = run.result.published
        if accepted is None or prices is None or published is None:
            raise EvidenceContractError(
                "REQ-G12-PYSPD-SURFACE: completed case lacks accepted output"
            )
        selected = case.specification
        solve_payload = accepted.solve_payload
        primary_snapshot = getattr(solve_payload, "primary_snapshot", None)
        pricing_snapshot = getattr(solve_payload, "pricing_snapshot", None)
        fixed_discrete = getattr(solve_payload, "fixed_discrete", {})
        fixed_sos_members = getattr(solve_payload, "fixed_sos_members", {})
        surfaces: dict[str, bytes] = {
            "case-selection": _json_bytes(
                {
                    "case_id": selected.case_id,
                    "date_time": selected.date_time,
                    "trading_period": selected.trading_period,
                    "study_mode": selected.study_mode,
                    "schedule_type": selected.schedule_type.value,
                    "interval_minutes": _number(selected.interval_minutes),
                    "publication_seconds": _number(selected.publication_seconds),
                    "ordinal": selected.ordinal,
                    "source_sha256": selected.source_sha256,
                }
            ),
            "state-transition": _json_bytes(
                {
                    "status": case.status.value,
                    "solve_count": case.solve_count,
                    "events": [
                        {
                            "sequence": event.sequence,
                            "kind": event.kind.value,
                            "case_id": event.case_id,
                            "solve_loop": event.solve_loop,
                            "details": _value(dict(event.details)),
                        }
                        for event in case.events
                    ],
                    "transfers": _mapping(case.transfers),
                    "untransferred_nodes": [
                        list(key) for key in sorted(case.untransferred_nodes)
                    ],
                }
            ),
            "primary-physics": _json_bytes(
                {
                    "generation": _mapping(accepted.generation),
                    "energy_shortfall": _mapping(accepted.energy_shortfall),
                    "bus_generation": _mapping(accepted.bus_generation),
                    "bus_load": _mapping(accepted.bus_load),
                    "final_required_load": _mapping(case.final_required_load),
                    "structural_signature": getattr(
                        primary_snapshot, "structural_signature", None
                    ),
                    "variables": _mapping(
                        getattr(primary_snapshot, "variables", {})
                    ),
                }
            ),
            "primary-objective": _json_bytes(
                {"objective_nzd": _number(accepted.objective)}
            ),
            "fixed-discrete-pricing-state": _json_bytes(
                {
                    "fixed_discrete": _mapping(fixed_discrete),
                    "fixed_sos_members": _mapping(fixed_sos_members),
                    "primary_structural_signature": getattr(
                        primary_snapshot, "structural_signature", None
                    ),
                    "pricing_structural_signature": getattr(
                        pricing_snapshot, "structural_signature", None
                    ),
                }
            ),
            "raw-bus-price": _json_bytes(_mapping(prices.raw_bus)),
            "repaired-bus-price": _json_bytes(_mapping(prices.repaired_bus)),
            "node-price": _json_bytes(_mapping(prices.node)),
            "reserve-price": _json_bytes(_mapping(prices.reserve)),
            "publication-seconds": _json_bytes(
                {
                    "trading_period": selected.trading_period,
                    "seconds": _number(selected.publication_seconds),
                }
            ),
            "rounded-published-output": _json_bytes(
                {
                    "energy": _mapping(
                        {
                            key: value
                            for key, value in published.energy.items()
                            if key[0] == selected.trading_period
                        }
                    ),
                    "reserve": _mapping(
                        {
                            key: value
                            for key, value in published.reserve.items()
                            if key[0] == selected.trading_period
                        }
                    ),
                    "total_seconds": _number(
                        published.total_seconds.get(selected.trading_period, 0.0)
                    ),
                }
            ),
            "report-field": self._report_surface(
                reports,
                case_id=selected.case_id,
                trading_period=selected.trading_period,
            ),
        }
        return CanonicalCaseSurfaces(selected.case_id, trading_date, surfaces)

    @staticmethod
    def _report_surface(
        reports: ReportBundle, *, case_id: str, trading_period: str
    ) -> bytes:
        tables: dict[str, object] = {}
        for name, table in sorted(reports.tables.items()):
            field_names = tuple(field.name for field in table.definition.fields)
            rows = []
            for row in table.rows:
                if "case_id" in row and row["case_id"] != case_id:
                    continue
                if (
                    "case_id" not in row
                    and "trading_period" in row
                    and row["trading_period"] != trading_period
                ):
                    continue
                rows.append(dict(row))
            tables[name] = {
                "fields": [
                    {"name": field.name, "unit": field.unit}
                    for field in table.definition.fields
                ],
                "rows": rows,
                "field_order": list(field_names),
            }
        return _json_bytes(tables)


def _mapping(values: Mapping[Any, Any]) -> list[dict[str, object]]:
    rows = []
    for key, value in values.items():
        identity = key if isinstance(key, tuple) else (key,)
        rows.append({"identity": [str(item) for item in identity], "value": _value(value)})
    return sorted(
        rows,
        key=lambda row: json.dumps(row["identity"], separators=(",", ":")),
    )


def _number(value: float) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise EvidenceContractError(
            "REQ-G12-PYSPD-SURFACE: non-finite numeric evidence"
        )
    return number.hex()


def _value(value: Any) -> object:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, Mapping):
        return {str(key): _value(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_value(item) for item in value]
    raise EvidenceContractError(
        f"REQ-G12-PYSPD-SURFACE: unsupported canonical value {type(value).__name__}"
    )


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
