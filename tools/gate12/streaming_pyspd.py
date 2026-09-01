"""Durable case-streaming PySPD replay for Gate 12 evidence production."""

from __future__ import annotations

import gc
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.orchestration import (
    DailyRunResult,
    DailyRunState,
    PublishedPriceAccumulator,
)
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.execution_provenance import python_execution_sha256
from tools.gate12.incremental_replay import IncrementalReplayWorkItem
from tools.gate12.pyspd_surfaces import (
    PARTIAL_E2E_SURFACES,
    CanonicalCaseSurfaces,
    CanonicalPartialCaseSurfaces,
    PyspdCaseSurfaceExporter,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _float_text(value: float) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise EvidenceContractError("REQ-G12-STREAM: non-finite checkpoint value")
    return number.hex()


def _float_value(value: object) -> float:
    if not isinstance(value, str):
        raise EvidenceContractError("REQ-G12-STREAM: checkpoint float is not text")
    try:
        number = float.fromhex(value)
    except ValueError as error:
        raise EvidenceContractError(
            "REQ-G12-STREAM: checkpoint float is invalid"
        ) from error
    if not math.isfinite(number):
        raise EvidenceContractError("REQ-G12-STREAM: non-finite checkpoint value")
    return number


def _mapping_rows[Key: tuple[str, ...]](
    values: Mapping[Key, float],
) -> list[dict[str, object]]:
    return [
        {"identity": list(key), "value": _float_text(value)}
        for key, value in sorted(values.items())
    ]


def _rows_mapping(rows: object, *, arity: int) -> dict[tuple[str, ...], float]:
    if not isinstance(rows, list):
        raise EvidenceContractError("REQ-G12-STREAM: checkpoint rows are invalid")
    output: dict[tuple[str, ...], float] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"identity", "value"}:
            raise EvidenceContractError("REQ-G12-STREAM: checkpoint row is invalid")
        identity = row["identity"]
        if (
            not isinstance(identity, list)
            or len(identity) != arity
            or any(not isinstance(item, str) or not item for item in identity)
        ):
            raise EvidenceContractError(
                "REQ-G12-STREAM: checkpoint identity is invalid"
            )
        key = tuple(identity)
        if key in output:
            raise EvidenceContractError("REQ-G12-STREAM: duplicate checkpoint identity")
        output[key] = _float_value(row["value"])
    return output


@dataclass(frozen=True, slots=True)
class PyspdReplayProgress:
    """Hash-bound daily replay state sufficient to resume without solved models."""

    work_item_sha256: str
    application_configuration_sha256: str
    execution_source_sha256: str
    next_case_ordinal: int
    last_completed_case_id: str | None
    previous_generation: Mapping[str, float]
    event_sequence: int
    energy_numerator: Mapping[tuple[str, str], float]
    reserve_numerator: Mapping[tuple[str, str, str], float]
    total_seconds: Mapping[str, float]
    period_date_time: Mapping[str, str]
    partial_surface_sha256: Mapping[str, Mapping[str, str]]
    partial_trading_period: Mapping[str, str]
    logical_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "previous_generation",
            MappingProxyType(dict(self.previous_generation)),
        )
        object.__setattr__(
            self, "energy_numerator", MappingProxyType(dict(self.energy_numerator))
        )
        object.__setattr__(
            self, "reserve_numerator", MappingProxyType(dict(self.reserve_numerator))
        )
        object.__setattr__(
            self, "total_seconds", MappingProxyType(dict(self.total_seconds))
        )
        object.__setattr__(
            self, "period_date_time", MappingProxyType(dict(self.period_date_time))
        )
        object.__setattr__(
            self,
            "partial_surface_sha256",
            MappingProxyType(
                {
                    case_id: MappingProxyType(dict(hashes))
                    for case_id, hashes in self.partial_surface_sha256.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "partial_trading_period",
            MappingProxyType(dict(self.partial_trading_period)),
        )

    @classmethod
    def create(
        cls,
        *,
        work_item_sha256: str,
        application_configuration_sha256: str,
        execution_source_sha256: str,
        next_case_ordinal: int = 0,
        last_completed_case_id: str | None = None,
        previous_generation: Mapping[str, float] | None = None,
        event_sequence: int = 0,
        energy_numerator: Mapping[tuple[str, str], float] | None = None,
        reserve_numerator: Mapping[tuple[str, str, str], float] | None = None,
        total_seconds: Mapping[str, float] | None = None,
        period_date_time: Mapping[str, str] | None = None,
        partial_surface_sha256: Mapping[str, Mapping[str, str]] | None = None,
        partial_trading_period: Mapping[str, str] | None = None,
    ) -> PyspdReplayProgress:
        unsigned = {
            "schema_version": 3,
            "work_item_sha256": work_item_sha256,
            "application_configuration_sha256": application_configuration_sha256,
            "execution_source_sha256": execution_source_sha256,
            "next_case_ordinal": next_case_ordinal,
            "last_completed_case_id": last_completed_case_id,
            "previous_generation": {
                key: _float_text(value)
                for key, value in sorted((previous_generation or {}).items())
            },
            "event_sequence": event_sequence,
            "energy_numerator": _mapping_rows(energy_numerator or {}),
            "reserve_numerator": _mapping_rows(reserve_numerator or {}),
            "total_seconds": {
                key: _float_text(value)
                for key, value in sorted((total_seconds or {}).items())
            },
            "period_date_time": dict(sorted((period_date_time or {}).items())),
            "partial_surface_sha256": {
                case_id: dict(sorted(hashes.items()))
                for case_id, hashes in sorted((partial_surface_sha256 or {}).items())
            },
            "partial_trading_period": dict(
                sorted((partial_trading_period or {}).items())
            ),
        }
        return cls(
            work_item_sha256=work_item_sha256,
            application_configuration_sha256=application_configuration_sha256,
            execution_source_sha256=execution_source_sha256,
            next_case_ordinal=next_case_ordinal,
            last_completed_case_id=last_completed_case_id,
            previous_generation=previous_generation or {},
            event_sequence=event_sequence,
            energy_numerator=energy_numerator or {},
            reserve_numerator=reserve_numerator or {},
            total_seconds=total_seconds or {},
            period_date_time=period_date_time or {},
            partial_surface_sha256=partial_surface_sha256 or {},
            partial_trading_period=partial_trading_period or {},
            logical_sha256=_logical_sha256(unsigned),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PyspdReplayProgress:
        expected = {
            "schema_version",
            "work_item_sha256",
            "application_configuration_sha256",
            "execution_source_sha256",
            "next_case_ordinal",
            "last_completed_case_id",
            "previous_generation",
            "event_sequence",
            "energy_numerator",
            "reserve_numerator",
            "total_seconds",
            "period_date_time",
            "partial_surface_sha256",
            "partial_trading_period",
            "logical_sha256",
        }
        if set(payload) != expected or payload.get("schema_version") != 3:
            raise EvidenceContractError("REQ-G12-STREAM: unexpected progress schema")
        previous = payload["previous_generation"]
        seconds = payload["total_seconds"]
        hashes = payload["partial_surface_sha256"]
        periods = payload["partial_trading_period"]
        period_date_time = payload["period_date_time"]
        if not all(
            isinstance(item, dict)
            for item in (previous, seconds, hashes, periods, period_date_time)
        ):
            raise EvidenceContractError("REQ-G12-STREAM: invalid progress mappings")
        return cls(
            work_item_sha256=str(payload["work_item_sha256"]),
            application_configuration_sha256=str(
                payload["application_configuration_sha256"]
            ),
            execution_source_sha256=str(payload["execution_source_sha256"]),
            next_case_ordinal=payload["next_case_ordinal"],
            last_completed_case_id=payload["last_completed_case_id"],
            previous_generation={
                str(key): _float_value(value) for key, value in previous.items()
            },
            event_sequence=payload["event_sequence"],
            energy_numerator=cast(
                dict[tuple[str, str], float],
                _rows_mapping(payload["energy_numerator"], arity=2),
            ),
            reserve_numerator=cast(
                dict[tuple[str, str, str], float],
                _rows_mapping(payload["reserve_numerator"], arity=3),
            ),
            total_seconds={
                str(key): _float_value(value) for key, value in seconds.items()
            },
            period_date_time={
                str(period): str(date_time)
                for period, date_time in period_date_time.items()
            },
            partial_surface_sha256={
                str(case_id): {str(name): str(value) for name, value in value.items()}
                for case_id, value in hashes.items()
                if isinstance(value, dict)
            },
            partial_trading_period={
                str(case_id): str(period) for case_id, period in periods.items()
            },
            logical_sha256=str(payload["logical_sha256"]),
        )

    def validate_for(
        self,
        work_item: IncrementalReplayWorkItem,
        configuration: ApplicationConfiguration,
        *,
        execution_source_sha256: str,
    ) -> None:
        if (
            not _SHA256.fullmatch(self.work_item_sha256)
            or not _SHA256.fullmatch(self.application_configuration_sha256)
            or not _SHA256.fullmatch(self.execution_source_sha256)
            or self.work_item_sha256 != work_item.logical_sha256
            or self.application_configuration_sha256 != configuration.logical_sha256
            or self.execution_source_sha256 != execution_source_sha256
            or isinstance(self.next_case_ordinal, bool)
            or not 0 <= self.next_case_ordinal <= len(work_item.case_ids)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise EvidenceContractError(
                "REQ-G12-STREAM: progress provenance or position mismatch"
            )
        expected_last = (
            work_item.case_ids[self.next_case_ordinal - 1]
            if self.next_case_ordinal
            else None
        )
        completed = set(work_item.case_ids[: self.next_case_ordinal])
        partial_ids = set(self.partial_surface_sha256)
        if (
            self.last_completed_case_id != expected_last
            or partial_ids != set(self.partial_trading_period)
            or not partial_ids.issubset(completed)
            or not partial_ids.issubset(work_item.affected_case_ids)
            or any(
                set(hashes) != PARTIAL_E2E_SURFACES
                or any(not _SHA256.fullmatch(value) for value in hashes.values())
                for hashes in self.partial_surface_sha256.values()
            )
        ):
            raise EvidenceContractError("REQ-G12-STREAM: progress prefix is invalid")
        if self.logical_sha256 != _logical_sha256(self.to_dict(include_hash=False)):
            raise EvidenceContractError("REQ-G12-STREAM: progress hash mismatch")

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 3,
            "work_item_sha256": self.work_item_sha256,
            "application_configuration_sha256": self.application_configuration_sha256,
            "execution_source_sha256": self.execution_source_sha256,
            "next_case_ordinal": self.next_case_ordinal,
            "last_completed_case_id": self.last_completed_case_id,
            "previous_generation": {
                key: _float_text(value)
                for key, value in sorted(self.previous_generation.items())
            },
            "event_sequence": self.event_sequence,
            "energy_numerator": _mapping_rows(self.energy_numerator),
            "reserve_numerator": _mapping_rows(self.reserve_numerator),
            "total_seconds": {
                key: _float_text(value)
                for key, value in sorted(self.total_seconds.items())
            },
            "period_date_time": dict(sorted(self.period_date_time.items())),
            "partial_surface_sha256": {
                case_id: dict(sorted(hashes.items()))
                for case_id, hashes in sorted(self.partial_surface_sha256.items())
            },
            "partial_trading_period": dict(sorted(self.partial_trading_period.items())),
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class PyspdReplayProgressStore:
    """Atomically persist and hash-verify one date's streaming progress."""

    def __init__(self, root: Path, trading_date: str) -> None:
        self.root = root / trading_date
        self.checkpoint_path = self.root / "checkpoint.json"

    def load(
        self,
        work_item: IncrementalReplayWorkItem,
        configuration: ApplicationConfiguration,
        *,
        execution_source_sha256: str,
    ) -> PyspdReplayProgress | None:
        if not self.checkpoint_path.exists():
            return None
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-STREAM: progress checkpoint is unreadable"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError("REQ-G12-STREAM: progress must be an object")
        progress = PyspdReplayProgress.from_dict(payload)
        progress.validate_for(
            work_item,
            configuration,
            execution_source_sha256=execution_source_sha256,
        )
        for case_id, hashes in progress.partial_surface_sha256.items():
            self._verify_case(case_id, hashes)
        return progress

    def write_checkpoint(self, progress: PyspdReplayProgress) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / "checkpoint.json.tmp"
        if temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-STREAM: stale temporary checkpoint exists"
            )
        temporary.write_text(
            json.dumps(progress.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.checkpoint_path)

    def write_partial(self, partial: CanonicalPartialCaseSurfaces) -> None:
        if partial.trading_date != self.root.name:
            raise EvidenceContractError("REQ-G12-STREAM: partial date mismatch")
        case_root = self.root / "cases"
        target = case_root / partial.case_id
        temporary = case_root / f"{partial.case_id}.tmp"
        if target.exists():
            self._verify_case(partial.case_id, partial.surface_sha256)
            return
        if temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-STREAM: stale temporary case evidence exists"
            )
        temporary.mkdir(parents=True)
        for surface, payload in sorted(partial.surfaces.items()):
            (temporary / f"{surface}.json").write_bytes(payload)
        temporary.replace(target)

    def load_partial(
        self,
        *,
        case_id: str,
        trading_period: str,
        hashes: Mapping[str, str],
    ) -> CanonicalPartialCaseSurfaces:
        self._verify_case(case_id, hashes)
        return CanonicalPartialCaseSurfaces(
            case_id,
            self.root.name,
            trading_period,
            {
                surface: (
                    self.root / "cases" / case_id / f"{surface}.json"
                ).read_bytes()
                for surface in sorted(PARTIAL_E2E_SURFACES)
            },
        )

    def _verify_case(self, case_id: str, hashes: Mapping[str, str]) -> None:
        if set(hashes) != PARTIAL_E2E_SURFACES:
            raise EvidenceContractError("REQ-G12-STREAM: partial hash set mismatch")
        for surface, expected in hashes.items():
            path = self.root / "cases" / case_id / f"{surface}.json"
            try:
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as error:
                raise EvidenceContractError(
                    "REQ-G12-STREAM: partial case evidence is unavailable"
                ) from error
            if actual != expected:
                raise EvidenceContractError(
                    "REQ-G12-STREAM: partial case evidence hash mismatch"
                )


class StreamingPyspdReplayRunner:
    """Solve, evidence-project, and checkpoint one daily prefix a case at a time."""

    def __init__(
        self,
        *,
        application: PyspdApplication | None = None,
        exporter: PyspdCaseSurfaceExporter | None = None,
    ) -> None:
        self.application = application or PyspdApplication()
        self.exporter = exporter or PyspdCaseSurfaceExporter()

    def run(
        self,
        *,
        configuration: ApplicationConfiguration,
        work_item: IncrementalReplayWorkItem,
        progress_root: Path,
    ) -> tuple[CanonicalCaseSurfaces, ...]:
        daily = self.application.daily_configuration(configuration)
        execution_source_sha256 = python_execution_sha256()
        store = PyspdReplayProgressStore(progress_root, work_item.trading_date)
        progress = store.load(
            work_item,
            configuration,
            execution_source_sha256=execution_source_sha256,
        ) or PyspdReplayProgress.create(
            work_item_sha256=work_item.logical_sha256,
            application_configuration_sha256=configuration.logical_sha256,
            execution_source_sha256=execution_source_sha256,
        )
        progress.validate_for(
            work_item,
            configuration,
            execution_source_sha256=execution_source_sha256,
        )
        accumulator = PublishedPriceAccumulator(
            energy_numerator=progress.energy_numerator,
            reserve_numerator=progress.reserve_numerator,
            total_seconds=progress.total_seconds,
            date_time=progress.period_date_time,
        )
        previous_generation = dict(progress.previous_generation)
        event_sequence = progress.event_sequence
        partial_hashes = {
            case_id: dict(hashes)
            for case_id, hashes in progress.partial_surface_sha256.items()
        }
        partial_periods = dict(progress.partial_trading_period)
        case_runner = self.application.case_runner(configuration)
        for ordinal, prepared in enumerate(
            self.application.iter_prepared_cases(
                configuration, start_ordinal=progress.next_case_ordinal
            ),
            start=progress.next_case_ordinal,
        ):
            expected_id = work_item.case_ids[ordinal]
            actual_id = prepared.specification.case_id
            if actual_id != expected_id:
                raise EvidenceContractError(
                    "REQ-G12-STREAM: prepared case order differs from work item"
                )
            print(
                f"PySPD {work_item.trading_date} case {ordinal + 1}/"
                f"{len(work_item.case_ids)} {actual_id}: solving",
                flush=True,
            )
            execution = case_runner.execute(
                daily,
                prepared,
                previous_generation=previous_generation,
                event_sequence=event_sequence,
            )
            accumulator.add(execution.result)
            if actual_id in work_item.affected_case_ids:
                one_case = DailyRunResult(
                    DailyRunState.COMPLETE,
                    daily.logical_sha256,
                    (execution.result,),
                    None,
                    execution.result.events,
                )
                reports = self.application.render_report_bundle(configuration, one_case)
                partial = self.exporter.export_partial(
                    execution.result,
                    reports,
                    trading_date=work_item.trading_date,
                )
                store.write_partial(partial)
                partial_hashes[actual_id] = partial.surface_sha256
                partial_periods[actual_id] = partial.trading_period
            previous_generation = execution.previous_generation
            event_sequence = execution.next_event_sequence
            progress = PyspdReplayProgress.create(
                work_item_sha256=work_item.logical_sha256,
                application_configuration_sha256=configuration.logical_sha256,
                execution_source_sha256=execution_source_sha256,
                next_case_ordinal=ordinal + 1,
                last_completed_case_id=actual_id,
                previous_generation=previous_generation,
                event_sequence=event_sequence,
                energy_numerator=accumulator.energy_numerator,
                reserve_numerator=accumulator.reserve_numerator,
                total_seconds=accumulator.total_seconds,
                period_date_time=accumulator.date_time,
                partial_surface_sha256=partial_hashes,
                partial_trading_period=partial_periods,
            )
            progress.validate_for(
                work_item,
                configuration,
                execution_source_sha256=execution_source_sha256,
            )
            store.write_checkpoint(progress)
            print(
                f"PySPD {work_item.trading_date} case {ordinal + 1}/"
                f"{len(work_item.case_ids)} {actual_id}: checkpointed",
                flush=True,
            )
            del execution, prepared
            gc.collect()
        published = accumulator.finish(decimals=configuration.price_rounding_decimals)
        if progress.next_case_ordinal != len(work_item.case_ids):
            raise EvidenceContractError(
                "REQ-G12-STREAM: replay stopped before prefix end"
            )
        return tuple(
            self.exporter.complete(
                store.load_partial(
                    case_id=case_id,
                    trading_period=progress.partial_trading_period[case_id],
                    hashes=progress.partial_surface_sha256[case_id],
                ),
                published,
            )
            for case_id in work_item.affected_case_ids
        )
