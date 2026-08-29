"""Immutable runtime configuration, case, identifier, and result contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from pyspd.data.raw import RawSymbols


class ContractError(ValueError):
    """A typed public contract is internally inconsistent."""


class OperationMode(StrEnum):
    SPD = "SPD"
    AUD = "AUD"
    DPS = "DPS"


@dataclass(frozen=True, slots=True)
class CaseIdentifier:
    case_id: str
    date_time: str
    trading_period: str

    def __post_init__(self) -> None:
        for name in ("case_id", "date_time", "trading_period"):
            if not getattr(self, name).strip():
                raise ContractError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class RunConfiguration:
    formulation_id: str
    operation_mode: OperationMode
    case_ids: tuple[str, ...]
    options: Mapping[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.formulation_id.strip():
            raise ContractError("formulation_id must not be empty")
        case_ids = tuple(self.case_ids)
        if len(set(case_ids)) != len(case_ids):
            raise ContractError("duplicate case identifier")
        if any(not case_id.strip() for case_id in case_ids):
            raise ContractError("case identifiers must not be empty")
        object.__setattr__(self, "case_ids", case_ids)
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


@dataclass(frozen=True, slots=True)
class CaseData:
    formulation_id: str
    identifier: CaseIdentifier
    symbols: RawSymbols

    def __post_init__(self) -> None:
        if not self.formulation_id.strip():
            raise ContractError("formulation_id must not be empty")
        case_id = self.identifier.case_id
        case_definitions = next(
            (
                symbol
                for symbol in self.symbols.symbols
                if symbol.name == "i_caseDefn"
            ),
            None,
        )
        if case_definitions is not None and case_id not in {
            record.keys[0] for record in case_definitions.records
        }:
            raise ContractError(f"case_id {case_id!r} is absent from i_caseDefn")
        for symbol in self.symbols.symbols:
            if symbol.domains and symbol.domains[0] in {"ca", "caseID"}:
                other = next(
                    (record.keys[0] for record in symbol.records if record.keys[0] != case_id),
                    None,
                )
                if other is not None:
                    raise ContractError(
                        f"{symbol.name} contains unselected case_id {other!r}"
                    )


class ResultQuality(StrEnum):
    VALID = "valid"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ResultField:
    name: str
    dimensions: tuple[str, ...]
    unit: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.unit.strip():
            raise ContractError("result field name and unit must not be empty")
        dimensions = tuple(self.dimensions)
        if len(set(dimensions)) != len(dimensions):
            raise ContractError(f"duplicate result dimension in {self.name}")
        object.__setattr__(self, "dimensions", dimensions)


@dataclass(frozen=True, slots=True)
class DataResultSchema:
    name: str
    formulation_id: str
    fields: tuple[ResultField, ...]

    def __post_init__(self) -> None:
        fields = tuple(self.fields)
        if not self.name.strip() or not self.formulation_id.strip():
            raise ContractError("result schema name and formulation must not be empty")
        if len({field.name for field in fields}) != len(fields):
            raise ContractError("duplicate result field")
        object.__setattr__(self, "fields", fields)


@dataclass(frozen=True, slots=True)
class ResultRecord:
    field: str
    keys: tuple[str, ...]
    value: float | None
    quality: ResultQuality = ResultQuality.VALID

    def __post_init__(self) -> None:
        object.__setattr__(self, "keys", tuple(self.keys))
        if self.value is not None and not math.isfinite(self.value):
            raise ContractError("result values must be finite or unavailable")
        if self.quality is ResultQuality.VALID and self.value is None:
            raise ContractError("valid result requires a value")
        if self.quality is ResultQuality.UNAVAILABLE and self.value is not None:
            raise ContractError("unavailable result cannot contain a value")


@dataclass(frozen=True, slots=True)
class ResultSet:
    schema: DataResultSchema
    records: tuple[ResultRecord, ...]

    def __post_init__(self) -> None:
        records = tuple(self.records)
        fields = {field.name: field for field in self.schema.fields}
        identities: set[tuple[str, tuple[str, ...]]] = set()
        for record in records:
            if record.field not in fields:
                raise ContractError(f"unknown result field: {record.field}")
            expected_dimension = len(fields[record.field].dimensions)
            if len(record.keys) != expected_dimension:
                raise ContractError(
                    f"key dimension mismatch for {record.field}: "
                    f"{len(record.keys)} != {expected_dimension}"
                )
            identity = (record.field, record.keys)
            if identity in identities:
                raise ContractError(f"duplicate result identity: {identity}")
            identities.add(identity)
        object.__setattr__(self, "records", records)
