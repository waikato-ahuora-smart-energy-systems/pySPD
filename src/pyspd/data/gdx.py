"""Optional GAMS Transfer adapter for governed raw-GDX conversion."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyspd.data.raw import RawRecord, RawSymbol, RawSymbols, SymbolType
from pyspd.data.values import ScalarValue, ValueKind

if TYPE_CHECKING:
    import pyarrow as pa

    from pyspd.data.feed import CanonicalFeed


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
    def write_feed(
        cls,
        path: Path,
        root: Path,
        *,
        system_directory: Path | None = None,
        compression: str = "zstd",
    ) -> CanonicalFeed:
        try:
            import gams.transfer as gt
        except ImportError as error:  # pragma: no cover - exercised by env contract
            raise RuntimeError(
                "GDX conversion requires the uv 'gdx' dependency group"
            ) from error
        from pyspd.data.feed import CanonicalFeed

        path = path.resolve()
        container = gt.Container(
            system_directory=str(system_directory.resolve())
            if system_directory is not None
            else None
        )
        container.read(str(path))
        return CanonicalFeed.write_tables(
            source_name=path.name,
            source_sha256=cls._file_sha256(path),
            items=cls._transfer_tables(container, gt.SpecialValues),
            root=root,
            compression=compression,
        )

    @classmethod
    def _transfer_tables(
        cls, container: Any, special_values: Any
    ) -> Iterator[tuple[dict[str, Any], pa.Table]]:
        import numpy as np
        import pyarrow as pa

        type_map = {
            "set": SymbolType.SET,
            "parameter": SymbolType.PARAMETER,
            "variable": SymbolType.VARIABLE,
            "equation": SymbolType.EQUATION,
            "alias": SymbolType.ALIAS,
        }
        predicates = (
            ("isEps", ValueKind.EPS.value),
            ("isNA", ValueKind.NA.value),
            ("isUndef", ValueKind.UNDEF.value),
            ("isPosInf", ValueKind.POSITIVE_INFINITY.value),
            ("isNegInf", ValueKind.NEGATIVE_INFINITY.value),
        )
        for name in container.listSymbols():
            source = container[name]
            dimension = int(source.dimension)
            frame = source.records
            has_columns = frame is not None and len(frame.columns) >= dimension
            uel_orders = (
                [
                    [str(uel) for uel in source.getUELs(dimensions=index)]
                    for index in range(dimension)
                ]
                if has_columns
                else [[] for _ in range(dimension)]
            )
            value_fields = (
                [str(column) for column in frame.columns[dimension:]]
                if has_columns
                else []
            )
            metadata = {
                "name": str(name),
                "symbol_type": type_map[type(source).__name__.lower()].value,
                "dimension": dimension,
                "domains": [str(domain) for domain in source.domain_names],
                "description": str(source.description),
                "uel_orders": uel_orders,
                "value_fields": value_fields,
            }
            count = 0 if frame is None else len(frame)
            columns: dict[str, Any] = {
                "record_ordinal": pa.array(range(count), type=pa.int64())
            }
            for index in range(dimension):
                values = [] if not has_columns else frame.iloc[:, index].astype(str)
                columns[f"key_{index}"] = pa.array(values, type=pa.string())
            for field_index, field_name in enumerate(value_fields, start=dimension):
                series = frame.iloc[:, field_index]
                if field_name == "element_text":
                    text = series.fillna("").astype(str)
                    columns[f"{field_name}__kind"] = pa.array(
                        [ValueKind.TEXT.value] * count, type=pa.string()
                    )
                    columns[f"{field_name}__number"] = pa.nulls(
                        count, type=pa.float64()
                    )
                    columns[f"{field_name}__text"] = pa.array(
                        text, type=pa.string()
                    )
                    continue
                numeric = np.asarray(series, dtype=np.float64)
                kinds = np.full(count, ValueKind.FINITE.value, dtype=object)
                special_mask = np.zeros(count, dtype=bool)
                for predicate, kind in predicates:
                    mask = np.asarray(
                        getattr(special_values, predicate)(numeric), dtype=bool
                    )
                    kinds[mask] = kind
                    special_mask |= mask
                if np.any(~special_mask & ~np.isfinite(numeric)):
                    raise ValueError(
                        f"{name}.{field_name} contains an unclassified non-finite value"
                    )
                numeric = numeric.copy()
                numeric[(~special_mask) & (numeric == 0.0)] = 0.0
                columns[f"{field_name}__kind"] = pa.array(kinds, type=pa.string())
                columns[f"{field_name}__number"] = pa.array(
                    numeric, mask=special_mask, type=pa.float64()
                )
                columns[f"{field_name}__text"] = pa.nulls(count, type=pa.string())
            yield metadata, pa.Table.from_pydict(columns)

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
                value_columns: dict[str, tuple[ScalarValue, ...]] = {}
                for index in range(dimension, len(columns)):
                    field_name = columns[index]
                    values = records_frame.iloc[:, index]
                    if field_name == "element_text":
                        value_columns[field_name] = tuple(
                            ScalarValue.text("" if value is None else str(value))
                            for value in values
                        )
                    else:
                        value_columns[field_name] = cls.classify_numeric_column(
                            values, special_values
                        )
                for row_index, row in enumerate(
                    records_frame.itertuples(index=False, name=None)
                ):
                    keys = tuple(str(value) for value in row[:dimension])
                    values = {
                        columns[index]: value_columns[columns[index]][row_index]
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
    def classify_numeric_column(
        values: Any, special_values: Any
    ) -> tuple[ScalarValue, ...]:
        """Classify one GDX value column with vectorized special-value tests."""

        import numpy as np

        numeric = np.asarray(values, dtype=np.float64)
        if numeric.ndim != 1:
            raise ValueError("GDX numeric value column must be one-dimensional")
        codes = np.zeros(len(numeric), dtype=np.uint8)
        predicates = (
            (1, "isEps", ValueKind.EPS),
            (2, "isNA", ValueKind.NA),
            (3, "isUndef", ValueKind.UNDEF),
            (4, "isPosInf", ValueKind.POSITIVE_INFINITY),
            (5, "isNegInf", ValueKind.NEGATIVE_INFINITY),
        )
        special_by_code: dict[int, ScalarValue] = {}
        for code, predicate, kind in predicates:
            detected = np.asarray(
                getattr(special_values, predicate)(numeric), dtype=bool
            )
            if detected.shape != numeric.shape:
                raise ValueError(
                    f"GDX {predicate} predicate returned an incompatible shape"
                )
            codes[(codes == 0) & detected] = code
            special_by_code[code] = ScalarValue.special(kind)
        finite = codes == 0
        if np.any(finite & ~np.isfinite(numeric)):
            raise ValueError("unclassified non-finite GDX numeric value")
        numeric = numeric.copy()
        numeric[finite & (numeric == 0.0)] = 0.0
        return tuple(
            ScalarValue.finite(float(value))
            if code == 0
            else special_by_code[int(code)]
            for value, code in zip(numeric, codes, strict=True)
        )

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
