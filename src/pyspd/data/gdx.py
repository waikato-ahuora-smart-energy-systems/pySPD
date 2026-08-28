"""Optional GAMS Transfer adapter for governed raw-GDX conversion."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.values import ScalarValue, ValueKind


class GdxAdapter:
    """Convert GAMS Transfer containers into immutable :class:`RawSymbols`."""

    @classmethod
    def read(cls, path: Path, *, system_directory: Path | None = None) -> RawSymbols:
        try:
            import gams.transfer as gt
        except ImportError as error:  # pragma: no cover - exercised by env contract
            raise RuntimeError(
                "GDX conversion requires the uv 'gdx' dependency group; "
                "canonical loading does not"
            ) from error
        path = path.resolve()
        container = gt.Container(
            system_directory=str(system_directory.resolve())
            if system_directory is not None
            else None
        )
        container.read(str(path))
        return cls.from_container(
            container,
            source_name=path.name,
            source_sha256=cls._file_sha256(path),
            special_values=gt.SpecialValues,
        )

    @classmethod
    def from_container(
        cls,
        container: Any,
        *,
        source_name: str,
        source_sha256: str,
        special_values: Any,
    ) -> RawSymbols:
        symbols: list[RawSymbol] = []
        type_map = {
            "set": SymbolType.SET,
            "parameter": SymbolType.PARAMETER,
            "variable": SymbolType.VARIABLE,
            "equation": SymbolType.EQUATION,
            "alias": SymbolType.ALIAS,
        }
        for name in container.listSymbols():
            source = container[name]
            class_name = type(source).__name__.lower()
            try:
                symbol_type = type_map[class_name]
            except KeyError as error:
                raise ValueError(f"unsupported GDX symbol type: {class_name}") from error
            dimension = int(source.dimension)
            domains = tuple(str(domain) for domain in source.domain_names)
            records_frame = source.records
            records: list[RawRecord] = []
            uel_orders: list[tuple[str, ...]] = []
            if records_frame is not None and len(records_frame.columns) >= dimension:
                uel_orders = [
                    tuple(str(uel) for uel in source.getUELs(dimensions=index))
                    for index in range(dimension)
                ]
                columns = [str(column) for column in records_frame.columns]
                for row in records_frame.itertuples(index=False, name=None):
                    keys = tuple(str(value) for value in row[:dimension])
                    values = {
                        columns[index]: (
                            ScalarValue.text("" if row[index] is None else str(row[index]))
                            if columns[index] == "element_text"
                            else cls.classify_numeric(row[index], special_values)
                        )
                        for index in range(dimension, len(columns))
                    }
                    records.append(RawRecord(keys, values))
            else:
                uel_orders = [() for _ in range(dimension)]
            symbols.append(
                RawSymbol(
                    name=str(name),
                    symbol_type=symbol_type,
                    dimension=dimension,
                    domains=domains,
                    description=str(source.description),
                    uel_orders=tuple(uel_orders),
                    records=tuple(records),
                )
            )
        return RawSymbols(source_name, source_sha256, tuple(symbols))

    @staticmethod
    def classify_numeric(value: Any, special_values: Any) -> ScalarValue:
        predicates = (
            ("isEps", ValueKind.EPS),
            ("isNA", ValueKind.NA),
            ("isUndef", ValueKind.UNDEF),
            ("isPosInf", ValueKind.POSITIVE_INFINITY),
            ("isNegInf", ValueKind.NEGATIVE_INFINITY),
        )
        for predicate, kind in predicates:
            if bool(getattr(special_values, predicate)(value)):
                return ScalarValue.special(kind)
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("unclassified non-finite GDX numeric value")
        return ScalarValue.finite(number)

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
