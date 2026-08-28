"""Versioned source-symbol catalog and fail-closed schema validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from pyspd.data.raw import RawSymbols, SymbolType


class SymbolCatalogError(ValueError):
    """Source symbols do not conform to their formulation catalog."""


@dataclass(frozen=True, slots=True)
class SymbolSpec:
    name: str
    aliases: tuple[str, ...]
    symbol_type: SymbolType
    dimension: int
    domains: tuple[str, ...]
    units: str
    consumer: str
    required: bool
    missingness: str
    ordering: str
    domain_variants: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class SymbolCatalog:
    formulation: str
    missingness: str
    ordering: str
    symbols: tuple[SymbolSpec, ...]

    @classmethod
    def vspd_v5(cls) -> SymbolCatalog:
        resource = files("pyspd.data").joinpath("catalogs/vspd-v5.0.6.json")
        return cls.from_payload(json.loads(resource.read_text(encoding="utf-8")))

    @classmethod
    def from_path(cls, path: Path) -> SymbolCatalog:
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SymbolCatalog:
        defaults = payload["defaults"]
        specifications = tuple(
            SymbolSpec(
                name=item["name"],
                aliases=tuple(item.get("aliases", ())),
                symbol_type=SymbolType(item["type"]),
                dimension=item["dimension"],
                domains=tuple(item["domains"]),
                units=item["units"],
                consumer=item["consumer"],
                required=item.get("required", True),
                missingness=item.get("missingness", defaults["missingness"]),
                ordering=item.get("ordering", defaults["ordering"]),
                domain_variants=tuple(
                    tuple(variant) for variant in item.get("domain_variants", ())
                ),
            )
            for item in payload["symbols"]
        )
        if payload["source_symbol_count"] != len(specifications):
            raise SymbolCatalogError("declared source-symbol count does not match")
        declared_names = [
            name for item in specifications for name in (item.name, *item.aliases)
        ]
        if len(set(declared_names)) != len(declared_names):
            raise SymbolCatalogError("catalog contains duplicate symbol names")
        return cls(
            formulation=payload["formulation"],
            missingness=defaults["missingness"],
            ordering=defaults["ordering"],
            symbols=specifications,
        )

    def validate(self, raw: RawSymbols) -> None:
        expected = {spec.name: spec for spec in self.symbols}
        aliases = {
            alias: spec.name for spec in self.symbols for alias in spec.aliases
        }
        actual: dict[str, Any] = {}
        for symbol in raw.symbols:
            canonical_name = aliases.get(symbol.name, symbol.name)
            if canonical_name in actual:
                raise SymbolCatalogError(
                    f"multiple source aliases supplied for {canonical_name}"
                )
            actual[canonical_name] = symbol
        missing = sorted(
            name
            for name in set(expected) - set(actual)
            if expected[name].required
        )
        unexpected = sorted(set(actual) - set(expected))
        if missing:
            raise SymbolCatalogError(f"missing symbols: {', '.join(missing)}")
        if unexpected:
            raise SymbolCatalogError(f"unexpected symbols: {', '.join(unexpected)}")
        for name, spec in expected.items():
            symbol = actual[name]
            if symbol.symbol_type is not spec.symbol_type:
                raise SymbolCatalogError(
                    f"type mismatch for {name}: {symbol.symbol_type} != {spec.symbol_type}"
                )
            if symbol.dimension != spec.dimension:
                raise SymbolCatalogError(
                    f"dimension mismatch for {name}: "
                    f"{symbol.dimension} != {spec.dimension}"
                )
            allowed_domains = (spec.domains, *spec.domain_variants)
            if not any(
                self._domains_equivalent(symbol.domains, variant)
                for variant in allowed_domains
            ):
                raise SymbolCatalogError(
                    f"domain mismatch for {name}: {symbol.domains} not in "
                    f"{allowed_domains}"
                )
            identities: set[tuple[str, ...]] = set()
            for record in symbol.records:
                if record.keys in identities:
                    raise SymbolCatalogError(
                        f"duplicate record identity in {name}: {record.keys}"
                    )
                identities.add(record.keys)
                for index, key in enumerate(record.keys):
                    if key not in symbol.uel_orders[index]:
                        raise SymbolCatalogError(
                            f"record key absent from UEL order in {name}[{index}]: {key}"
                        )

    @staticmethod
    def _domains_equivalent(
        actual: tuple[str, ...], expected: tuple[str, ...]
    ) -> bool:
        if actual == expected:
            return True
        semantics = {
            "ca": {"ca", "caseID"},
            "cn": {"cn", "caseName"},
            "rundt": {"rundt", "runDateTime"},
            "dt": {"dt", "dateTime"},
            "dtPar": {"dtPar", "*"},
            "tp": {"tp", "tradePeriod"},
            "casePar": {"casePar", "*"},
            "isl": {"isl", "island"},
            "islPar": {"islPar", "*"},
            "n": {"n", "node"},
            "n1": {"n1", "node"},
            "nodePar": {"nodePar", "*"},
            "b": {"b", "bus"},
            "b1": {"b1", "bus"},
            "b2": {"b2", "bus"},
            "br": {"br", "branch"},
            "brPar": {"brPar", "*"},
            "brCstr": {"brCstr", "branchConstraint"},
            "CstrRHS": {"CstrRHS", "*"},
            "o": {"o", "offer"},
            "o1": {"o1", "offer"},
            "trdr": {"trdr", "trader"},
            "offerPar": {"offerPar", "*"},
            "rg": {"rg", "riskGroup"},
            "riskC": {"riskC", "riskClass"},
            "blk": {"blk", "block", "*"},
            "bidofrCmpnt": {"bidofrCmpnt", "*"},
            "bd": {"bd", "bid"},
            "bidPar": {"bidPar", "*"},
            "MnodeCstr": {"MnodeCstr", "MnodeConstraint"},
            "riskPar": {"riskPar", "*"},
            "resPar": {"resPar", "*"},
        }
        return len(actual) == len(expected) and all(
            found in semantics.get(required, {required})
            for found, required in zip(actual, expected, strict=True)
        )
