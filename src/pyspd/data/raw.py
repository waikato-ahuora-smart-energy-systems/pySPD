"""Immutable faithful representation of ordered sparse GDX symbols."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from pyspd.data.values import ScalarValue


class SymbolType(StrEnum):
    SET = "set"
    PARAMETER = "parameter"
    VARIABLE = "variable"
    EQUATION = "equation"
    ALIAS = "alias"


@dataclass(frozen=True, slots=True)
class RawRecord:
    keys: tuple[str, ...]
    values: Mapping[str, ScalarValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "keys", tuple(self.keys))
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True, slots=True)
class RawSymbol:
    name: str
    symbol_type: SymbolType
    dimension: int
    domains: tuple[str, ...]
    description: str
    uel_orders: tuple[tuple[str, ...], ...]
    records: tuple[RawRecord, ...]

    def __post_init__(self) -> None:
        if self.dimension != len(self.domains):
            raise ValueError(f"{self.name}: dimension/domain mismatch")
        if self.dimension != len(self.uel_orders):
            raise ValueError(f"{self.name}: dimension/UEL-order mismatch")
        records = tuple(self.records)
        if any(len(record.keys) != self.dimension for record in records):
            raise ValueError(f"{self.name}: record key dimension mismatch")
        object.__setattr__(self, "domains", tuple(self.domains))
        object.__setattr__(
            self, "uel_orders", tuple(tuple(order) for order in self.uel_orders)
        )
        object.__setattr__(self, "records", records)


@dataclass(frozen=True, slots=True)
class RawSymbols:
    source_name: str
    source_sha256: str
    symbols: tuple[RawSymbol, ...]
    _by_name: Mapping[str, RawSymbol] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256")
        symbols = tuple(self.symbols)
        by_name = {symbol.name: symbol for symbol in symbols}
        if len(by_name) != len(symbols):
            raise ValueError("duplicate symbol name")
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))

    def __getitem__(self, name: str) -> RawSymbol:
        return self._by_name[name]

    @property
    def logical_sha256(self) -> str:
        encoded = json.dumps(
            self.to_logical_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_logical_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_name": self.source_name,
            "source_sha256": self.source_sha256,
            "symbols": [
                {
                    "name": symbol.name,
                    "symbol_type": symbol.symbol_type.value,
                    "dimension": symbol.dimension,
                    "domains": list(symbol.domains),
                    "description": symbol.description,
                    "uel_orders": [list(order) for order in symbol.uel_orders],
                    "records": [
                        {
                            "keys": list(record.keys),
                            "values": {
                                name: value.to_wire()
                                for name, value in record.values.items()
                            },
                        }
                        for record in symbol.records
                    ],
                }
                for symbol in self.symbols
            ],
        }
