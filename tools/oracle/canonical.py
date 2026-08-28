"""Canonical, deterministic evidence for GDX symbols and linear matrices."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class SpecialValueClassifier(Protocol):
    @staticmethod
    def isEps(value: Any) -> bool: ...

    @staticmethod
    def isNA(value: Any) -> bool: ...

    @staticmethod
    def isUndef(value: Any) -> bool: ...

    @staticmethod
    def isPosInf(value: Any) -> bool: ...

    @staticmethod
    def isNegInf(value: Any) -> bool: ...


def canonical_value(
    value: Any,
    special_values: SpecialValueClassifier | None = None,
) -> dict[str, Any]:
    """Encode a scalar without losing float or GAMS special-value identity."""

    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if value is None:
        return {"kind": "null"}
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, int):
        return {"kind": "integer", "value": value}
    if isinstance(value, float):
        if special_values is not None:
            classifiers = (
                ("eps", special_values.isEps),
                ("na", special_values.isNA),
                ("undef", special_values.isUndef),
                ("posinf", special_values.isPosInf),
                ("neginf", special_values.isNegInf),
            )
            for kind, predicate in classifiers:
                if bool(predicate(value)):
                    return {"kind": kind}
        if value == 0.0 and math.copysign(1.0, value) < 0:
            return {"kind": "eps"}
        if math.isnan(value):
            return {"kind": "nan"}
        if value == math.inf:
            return {"kind": "posinf"}
        if value == -math.inf:
            return {"kind": "neginf"}
        return {"kind": "finite", "hex": value.hex()}
    if isinstance(value, bytes):
        return {"kind": "bytes", "hex": value.hex()}
    return {"kind": "string", "value": str(value)}


@dataclass(frozen=True)
class SymbolSnapshot:
    name: str
    kind: str
    subtype: str | None
    domain: tuple[str, ...]
    description: str
    columns: tuple[str, ...]
    records: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class CanonicalSymbolEvidence:
    name: str
    kind: str
    subtype: str | None
    domain: tuple[str, ...]
    description: str
    columns: tuple[str, ...]
    record_count: int
    ordered_sha256: str
    content_sha256: str


@dataclass(frozen=True)
class CanonicalGdxEvidence:
    symbol_count: int
    uel_count: int
    uels_ordered_sha256: str
    symbols: tuple[CanonicalSymbolEvidence, ...]
    logical_sha256: str

    @classmethod
    def from_snapshots(
        cls,
        snapshots: Sequence[SymbolSnapshot],
        uels: Sequence[str],
        special_values: SpecialValueClassifier | None = None,
    ) -> CanonicalGdxEvidence:
        symbol_evidence: list[CanonicalSymbolEvidence] = []
        for snapshot in snapshots:
            records = [
                [canonical_value(value, special_values) for value in row]
                for row in snapshot.records
            ]
            sorted_records = sorted(
                records,
                key=lambda row: json.dumps(
                    row,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
            symbol_evidence.append(
                CanonicalSymbolEvidence(
                    name=snapshot.name,
                    kind=snapshot.kind,
                    subtype=snapshot.subtype,
                    domain=snapshot.domain,
                    description=snapshot.description,
                    columns=snapshot.columns,
                    record_count=len(records),
                    ordered_sha256=_sha256(records),
                    content_sha256=_sha256(sorted_records),
                )
            )
        uel_values = [str(uel) for uel in uels]
        payload = {
            "uels": uel_values,
            "symbols": [asdict(symbol) for symbol in symbol_evidence],
        }
        return cls(
            symbol_count=len(symbol_evidence),
            uel_count=len(uel_values),
            uels_ordered_sha256=_sha256(uel_values),
            symbols=tuple(symbol_evidence),
            logical_sha256=_sha256(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GdxCanonicalizer:
    """Read a GDX through GAMS Transfer and emit a compact canonical manifest."""

    def __init__(self, system_directory: Path | None = None) -> None:
        self.system_directory = system_directory

    def read(
        self, path: Path, symbols: Sequence[str] | None = None
    ) -> CanonicalGdxEvidence:
        try:
            import gams.transfer as gt  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError(
                "GDX canonicalization requires the uv oracle dependency group"
            ) from error

        container = gt.Container(
            system_directory=(
                str(self.system_directory)
                if self.system_directory is not None
                else None
            )
        )
        container.read(
            str(path), symbols=list(symbols) if symbols is not None else None
        )
        snapshots: list[SymbolSnapshot] = []
        for name in container.listSymbols():
            symbol = container[name]
            records = symbol.records
            rows = (
                tuple(tuple(row) for row in records.itertuples(index=False, name=None))
                if records is not None
                else ()
            )
            snapshots.append(
                SymbolSnapshot(
                    name=name,
                    kind=type(symbol).__name__.lower(),
                    subtype=(str(symbol.type) if hasattr(symbol, "type") else None),
                    domain=tuple(symbol.domain_names),
                    description=str(symbol.description),
                    columns=(
                        tuple(str(column) for column in records.columns)
                        if records is not None
                        else ()
                    ),
                    records=rows,
                )
            )
        return CanonicalGdxEvidence.from_snapshots(
            snapshots,
            tuple(str(uel) for uel in container.getUELs()),
            gt.SpecialValues,
        )

    def write_manifest(
        self,
        source: Path,
        destination: Path,
        symbols: Sequence[str] | None = None,
    ) -> CanonicalGdxEvidence:
        evidence = self.read(source, symbols)
        destination.write_text(
            json.dumps(evidence.to_dict(), indent=2, sort_keys=True) + "\n"
        )
        return evidence


@dataclass(frozen=True)
class MatrixRow:
    name: str
    lower: float
    upper: float
    marginal: float
    level: float | None = None


@dataclass(frozen=True)
class MatrixColumn:
    name: str
    lower: float
    upper: float
    objective: float
    level: float
    reduced_cost: float
    discrete_type: str


@dataclass(frozen=True)
class MatrixEntry:
    row: str
    column: str
    coefficient: float


@dataclass(frozen=True)
class LinearMatrixEvidence:
    sense: str
    rows: tuple[MatrixRow, ...]
    columns: tuple[MatrixColumn, ...]
    entries: tuple[MatrixEntry, ...]
    nonzero_count: int
    structural_sha256: str
    logical_sha256: str

    @classmethod
    def build(
        cls,
        rows: Sequence[MatrixRow],
        columns: Sequence[MatrixColumn],
        entries: Sequence[MatrixEntry],
        sense: str,
    ) -> LinearMatrixEvidence:
        if sense not in {"minimize", "maximize"}:
            raise ValueError(f"unsupported objective sense: {sense!r}")
        row_map = {row.name: row for row in rows}
        column_map = {column.name: column for column in columns}
        if len(row_map) != len(rows):
            raise ValueError("duplicate matrix row")
        if len(column_map) != len(columns):
            raise ValueError("duplicate matrix column")
        coefficient_keys = [(entry.row, entry.column) for entry in entries]
        if len(set(coefficient_keys)) != len(coefficient_keys):
            raise ValueError("duplicate matrix coefficient")
        unknown = [
            key
            for key in coefficient_keys
            if key[0] not in row_map or key[1] not in column_map
        ]
        if unknown:
            raise ValueError(f"matrix coefficients reference unknown names: {unknown}")
        sorted_rows = tuple(sorted(rows, key=lambda row: row.name))
        sorted_columns = tuple(sorted(columns, key=lambda column: column.name))
        sorted_entries = tuple(
            sorted(entries, key=lambda entry: (entry.row, entry.column))
        )
        payload = {
            "sense": sense,
            "rows": [_canonical_dataclass(row) for row in sorted_rows],
            "columns": [_canonical_dataclass(column) for column in sorted_columns],
            "entries": [_canonical_dataclass(entry) for entry in sorted_entries],
        }
        structural_payload = {
            "sense": sense,
            "rows": [
                {
                    "name": canonical_value(row.name),
                    "lower": canonical_value(row.lower),
                    "upper": canonical_value(row.upper),
                }
                for row in sorted_rows
            ],
            "columns": [
                {
                    "name": canonical_value(column.name),
                    "lower": canonical_value(column.lower),
                    "upper": canonical_value(column.upper),
                    "objective": canonical_value(column.objective),
                    "discrete_type": canonical_value(column.discrete_type),
                }
                for column in sorted_columns
            ],
            "entries": [_canonical_dataclass(entry) for entry in sorted_entries],
        }
        return cls(
            sense=sense,
            rows=sorted_rows,
            columns=sorted_columns,
            entries=sorted_entries,
            nonzero_count=len(sorted_entries),
            structural_sha256=_sha256(structural_payload),
            logical_sha256=_sha256(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticNameDictionary:
    """Stable equation/variable names recovered from a Convert DictMap GDX."""

    rows: tuple[tuple[str, str], ...]
    columns: tuple[tuple[str, str], ...]
    logical_sha256: str

    @classmethod
    def build(
        cls,
        rows: Sequence[tuple[str, str]],
        columns: Sequence[tuple[str, str]],
    ) -> SemanticNameDictionary:
        sorted_rows = tuple(sorted(rows))
        sorted_columns = tuple(sorted(columns))
        cls._validate_mapping(sorted_rows, "row")
        cls._validate_mapping(sorted_columns, "column")
        payload = {"rows": sorted_rows, "columns": sorted_columns}
        return cls(sorted_rows, sorted_columns, _sha256(payload))

    @staticmethod
    def _validate_mapping(
        mapping: Sequence[tuple[str, str]], kind: str
    ) -> None:
        scalar_names = [scalar for scalar, _ in mapping]
        semantic_names = [semantic for _, semantic in mapping]
        if len(set(scalar_names)) != len(scalar_names):
            raise ValueError(f"duplicate scalar {kind} name in Convert dictionary")
        if len(set(semantic_names)) != len(semantic_names):
            raise ValueError(f"duplicate semantic {kind} name in Convert dictionary")

    def apply(self, matrix: LinearMatrixEvidence) -> LinearMatrixEvidence:
        """Replace Convert scalar identifiers, rejecting incomplete dictionaries."""

        row_names = dict(self.rows)
        column_names = dict(self.columns)
        missing_rows = sorted({row.name for row in matrix.rows} - row_names.keys())
        missing_columns = sorted(
            {column.name for column in matrix.columns} - column_names.keys()
        )
        if missing_rows or missing_columns:
            raise ValueError(
                "Convert dictionary does not cover matrix names: "
                f"rows={missing_rows}, columns={missing_columns}"
            )
        return LinearMatrixEvidence.build(
            rows=tuple(
                MatrixRow(
                    name=row_names[row.name],
                    lower=row.lower,
                    upper=row.upper,
                    marginal=row.marginal,
                    level=row.level,
                )
                for row in matrix.rows
            ),
            columns=tuple(
                MatrixColumn(
                    name=column_names[column.name],
                    lower=column.lower,
                    upper=column.upper,
                    objective=column.objective,
                    level=column.level,
                    reduced_cost=column.reduced_cost,
                    discrete_type=column.discrete_type,
                )
                for column in matrix.columns
            ),
            entries=tuple(
                MatrixEntry(
                    row=row_names[entry.row],
                    column=column_names[entry.column],
                    coefficient=entry.coefficient,
                )
                for entry in matrix.entries
            ),
            sense=matrix.sense,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IncrementalMatrixTransforms:
    """Approved algebraic transforms for Stage 4--7 projection comparisons."""

    @staticmethod
    def signed_row(
        row: MatrixRow,
        entries: Sequence[MatrixEntry],
        sign: int,
    ) -> tuple[MatrixRow, tuple[MatrixEntry, ...]]:
        if sign not in {-1, 1}:
            raise ValueError("row sign must be -1 or 1")
        if any(entry.row != row.name for entry in entries):
            raise ValueError("signed-row entries must all belong to the row")
        transformed_bounds = (sign * row.lower, sign * row.upper)
        transformed = MatrixRow(
            name=row.name,
            lower=min(transformed_bounds),
            upper=max(transformed_bounds),
            marginal=sign * row.marginal,
            level=(sign * row.level if row.level is not None else None),
        )
        return transformed, tuple(
            MatrixEntry(entry.row, entry.column, sign * entry.coefficient)
            for entry in entries
        )

    @staticmethod
    def recombine_ranged_dual(
        lower_multiplier: float,
        upper_multiplier: float,
    ) -> float:
        if (
            lower_multiplier < 0
            or upper_multiplier < 0
            or not math.isfinite(lower_multiplier)
            or not math.isfinite(upper_multiplier)
        ):
            raise ValueError("split-row multipliers must be finite and non-negative")
        return upper_multiplier - lower_multiplier


@dataclass(frozen=True)
class LinearMatrixValidation:
    row_count: int
    column_count: int
    nonzero_count: int
    max_activity_delta: float
    max_row_bound_violation: float
    max_column_bound_violation: float
    max_stationarity_residual: float
    max_scaled_stationarity_residual: float
    max_regular_stationarity_residual: float
    max_free_zero_objective_stationarity_residual: float
    max_row_complementarity: float
    max_column_complementarity: float
    max_scaled_complementarity: float
    max_dual_sign_violation: float
    absolute_tolerance: float
    stationarity_scale_floor: float
    scaled_stationarity_tolerance: float
    free_zero_objective_stationarity_tolerance: float
    scaled_complementarity_tolerance: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LinearMatrixValidator:
    """Independently recompute primal activity, bounds, and LP stationarity."""

    @staticmethod
    def validate(
        matrix: LinearMatrixEvidence,
        absolute_tolerance: float = 1e-7,
        stationarity_scale_floor: float = 1.0,
        scaled_stationarity_tolerance: float = 1e-7,
        free_zero_objective_stationarity_tolerance: float = 1e-4,
        scaled_complementarity_tolerance: float = 1e-6,
    ) -> LinearMatrixValidation:
        if absolute_tolerance < 0 or not math.isfinite(absolute_tolerance):
            raise ValueError("absolute_tolerance must be finite and non-negative")
        if (
            stationarity_scale_floor <= 0
            or not math.isfinite(stationarity_scale_floor)
        ):
            raise ValueError("stationarity_scale_floor must be finite and positive")
        if (
            scaled_stationarity_tolerance < 0
            or not math.isfinite(scaled_stationarity_tolerance)
        ):
            raise ValueError(
                "scaled_stationarity_tolerance must be finite and non-negative"
            )
        if (
            free_zero_objective_stationarity_tolerance < 0
            or not math.isfinite(free_zero_objective_stationarity_tolerance)
        ):
            raise ValueError(
                "free_zero_objective_stationarity_tolerance must be finite "
                "and non-negative"
            )
        if (
            scaled_complementarity_tolerance < 0
            or not math.isfinite(scaled_complementarity_tolerance)
        ):
            raise ValueError(
                "scaled_complementarity_tolerance must be finite and non-negative"
            )
        columns = {column.name: column for column in matrix.columns}
        activities = {row.name: 0.0 for row in matrix.rows}
        dual_products = {column.name: 0.0 for column in matrix.columns}
        maximum_coefficients = {column.name: 0.0 for column in matrix.columns}
        row_absolute_terms = {row.name: 0.0 for row in matrix.rows}
        row_marginals = {row.name: row.marginal for row in matrix.rows}
        for entry in matrix.entries:
            activities[entry.row] += entry.coefficient * columns[entry.column].level
            dual_products[entry.column] += entry.coefficient * row_marginals[entry.row]
            maximum_coefficients[entry.column] = max(
                maximum_coefficients[entry.column],
                abs(entry.coefficient),
            )
            row_absolute_terms[entry.row] += abs(
                entry.coefficient * columns[entry.column].level
            )
        activity_delta = max(
            (
                abs(activities[row.name] - row.level)
                if row.level is not None
                else 0.0
                for row in matrix.rows
            ),
            default=0.0,
        )
        row_bound_violation = max(
            (
                _bound_violation(activities[row.name], row.lower, row.upper)
                for row in matrix.rows
            ),
            default=0.0,
        )
        column_bound_violation = max(
            (
                _bound_violation(column.level, column.lower, column.upper)
                for column in matrix.columns
            ),
            default=0.0,
        )
        direction = 1.0 if matrix.sense == "maximize" else -1.0
        stationarity_residuals = {
            column.name: abs(
                direction * column.objective
                - dual_products[column.name]
                - column.reduced_cost
            )
            for column in matrix.columns
        }
        stationarity_scales = {
            column.name: max(
                stationarity_scale_floor,
                abs(column.objective),
                abs(column.reduced_cost),
                maximum_coefficients[column.name],
            )
            for column in matrix.columns
        }
        scaled_stationarity = max(
            (
                residual / stationarity_scales[name]
                for name, residual in stationarity_residuals.items()
            ),
            default=0.0,
        )
        free_zero_objective_columns = {
            column.name
            for column in matrix.columns
            if column.lower == -math.inf
            and column.upper == math.inf
            and column.objective == 0.0
        }
        free_stationarity = max(
            (
                residual
                for name, residual in stationarity_residuals.items()
                if name in free_zero_objective_columns
            ),
            default=0.0,
        )
        regular_stationarity = max(
            (
                residual
                for name, residual in stationarity_residuals.items()
                if name not in free_zero_objective_columns
            ),
            default=0.0,
        )
        stationarity = max(free_stationarity, regular_stationarity)

        row_complementarity: list[float] = []
        column_complementarity: list[float] = []
        scaled_complementarity: list[float] = []
        dual_sign_violations: list[float] = []

        for row in matrix.rows:
            activity = activities[row.name]
            finite_lower = math.isfinite(row.lower)
            finite_upper = math.isfinite(row.upper)
            equality = finite_lower and finite_upper and row.lower == row.upper
            if not finite_lower and not finite_upper:
                dual_sign_violations.append(abs(row.marginal))
            elif finite_lower and not finite_upper:
                dual_sign_violations.append(max(row.marginal, 0.0))
            elif finite_upper and not finite_lower:
                dual_sign_violations.append(max(-row.marginal, 0.0))
            if equality:
                continue
            primal_scale = max(
                1.0,
                abs(activity),
                row_absolute_terms[row.name],
                abs(row.lower) if finite_lower else 0.0,
                abs(row.upper) if finite_upper else 0.0,
            )
            dual_scale = max(1.0, abs(row.marginal))
            if finite_lower:
                product = max(-row.marginal, 0.0) * (activity - row.lower)
                row_complementarity.append(abs(product))
                scaled_complementarity.append(
                    abs(product) / (primal_scale * dual_scale)
                )
            if finite_upper:
                product = max(row.marginal, 0.0) * (row.upper - activity)
                row_complementarity.append(abs(product))
                scaled_complementarity.append(
                    abs(product) / (primal_scale * dual_scale)
                )

        for column in matrix.columns:
            finite_lower = math.isfinite(column.lower)
            finite_upper = math.isfinite(column.upper)
            fixed = finite_lower and finite_upper and column.lower == column.upper
            if not finite_lower and not finite_upper:
                dual_sign_violations.append(abs(column.reduced_cost))
            elif finite_lower and not finite_upper:
                dual_sign_violations.append(max(column.reduced_cost, 0.0))
            elif finite_upper and not finite_lower:
                dual_sign_violations.append(max(-column.reduced_cost, 0.0))
            if fixed:
                continue
            primal_scale = max(
                1.0,
                abs(column.level),
                abs(column.lower) if finite_lower else 0.0,
                abs(column.upper) if finite_upper else 0.0,
            )
            dual_scale = max(1.0, abs(column.reduced_cost))
            if finite_lower:
                product = max(-column.reduced_cost, 0.0) * (
                    column.level - column.lower
                )
                column_complementarity.append(abs(product))
                scaled_complementarity.append(
                    abs(product) / (primal_scale * dual_scale)
                )
            if finite_upper:
                product = max(column.reduced_cost, 0.0) * (
                    column.upper - column.level
                )
                column_complementarity.append(abs(product))
                scaled_complementarity.append(
                    abs(product) / (primal_scale * dual_scale)
                )

        max_row_complementarity = max(row_complementarity, default=0.0)
        max_column_complementarity = max(column_complementarity, default=0.0)
        max_scaled_complementarity = max(scaled_complementarity, default=0.0)
        max_dual_sign_violation = max(dual_sign_violations, default=0.0)
        passed = (
            max(
                activity_delta,
                row_bound_violation,
                column_bound_violation,
                regular_stationarity,
                max_dual_sign_violation,
            )
            <= absolute_tolerance
            and scaled_stationarity <= scaled_stationarity_tolerance
            and free_stationarity
            <= free_zero_objective_stationarity_tolerance
            and max_scaled_complementarity
            <= scaled_complementarity_tolerance
        )
        return LinearMatrixValidation(
            row_count=len(matrix.rows),
            column_count=len(matrix.columns),
            nonzero_count=matrix.nonzero_count,
            max_activity_delta=activity_delta,
            max_row_bound_violation=row_bound_violation,
            max_column_bound_violation=column_bound_violation,
            max_stationarity_residual=stationarity,
            max_scaled_stationarity_residual=scaled_stationarity,
            max_regular_stationarity_residual=regular_stationarity,
            max_free_zero_objective_stationarity_residual=free_stationarity,
            max_row_complementarity=max_row_complementarity,
            max_column_complementarity=max_column_complementarity,
            max_scaled_complementarity=max_scaled_complementarity,
            max_dual_sign_violation=max_dual_sign_violation,
            absolute_tolerance=absolute_tolerance,
            stationarity_scale_floor=stationarity_scale_floor,
            scaled_stationarity_tolerance=scaled_stationarity_tolerance,
            free_zero_objective_stationarity_tolerance=(
                free_zero_objective_stationarity_tolerance
            ),
            scaled_complementarity_tolerance=scaled_complementarity_tolerance,
            passed=passed,
        )


class ConvertMatrixReader:
    """Read the documented GAMS Convert DumpGDX linear-matrix schema."""

    _required: ClassVar[set[str]] = {
        "i",
        "j",
        "iobj",
        "jobj",
        "objcoef",
        "objjacval",
        "e",
        "x",
        "A",
    }

    def __init__(self, system_directory: Path | None = None) -> None:
        self.system_directory = system_directory

    def read(self, path: Path) -> LinearMatrixEvidence:
        try:
            import gams.transfer as gt  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError(
                "GDX matrix reading requires the uv oracle dependency group"
            ) from error
        container = gt.Container(
            system_directory=(
                str(self.system_directory)
                if self.system_directory is not None
                else None
            )
        )
        container.read(str(path))
        names = set(container.listSymbols())
        missing = sorted(self._required - names)
        if missing:
            raise ValueError(f"Convert GDX is missing symbols: {missing}")
        objective_row = str(container["iobj"].records.iloc[0]["i"])
        objective_column = str(container["jobj"].records.iloc[0]["j"])
        objective_scale = float(container["objjacval"].records.iloc[0]["value"])
        if objective_scale == 0:
            raise ValueError("Convert objective Jacobian is zero")
        objective_marker = float(container["objcoef"].records.iloc[0]["value"])
        if objective_marker not in {-1.0, 1.0}:
            raise ValueError(
                f"unsupported Convert objective marker: {objective_marker}"
            )
        sense = "maximize" if objective_marker == -1.0 else "minimize"

        coefficient_records = container["A"].records
        objective = {
            str(record.j): -float(record.value) / objective_scale
            for record in coefficient_records.itertuples(index=False)
            if str(record.i) == objective_row and str(record.j) != objective_column
        }
        rows = tuple(
            MatrixRow(
                name=str(record.i),
                lower=float(record.lower),
                upper=float(record.upper),
                marginal=float(record.marginal),
                level=float(record.level),
            )
            for record in container["e"].records.itertuples(index=False)
            if str(record.i) != objective_row
        )
        discrete = self._discrete_types(container)
        columns = tuple(
            MatrixColumn(
                name=str(record.j),
                lower=float(record.lower),
                upper=float(record.upper),
                objective=objective.get(str(record.j), 0.0),
                level=float(record.level),
                reduced_cost=float(record.marginal),
                discrete_type=discrete.get(str(record.j), "continuous"),
            )
            for record in container["x"].records.itertuples(index=False)
            if str(record.j) != objective_column
        )
        entries = tuple(
            MatrixEntry(str(record.i), str(record.j), float(record.value))
            for record in coefficient_records.itertuples(index=False)
            if str(record.i) != objective_row and str(record.j) != objective_column
        )
        return LinearMatrixEvidence.build(rows, columns, entries, sense)

    @staticmethod
    def _discrete_types(container: Any) -> dict[str, str]:
        result: dict[str, str] = {}
        for symbol_name, kind in (
            ("jb", "binary"),
            ("ji", "integer"),
            ("jsc", "semicontinuous"),
            ("jsi", "semiinteger"),
        ):
            if symbol_name not in container or container[symbol_name].records is None:
                continue
            for record in container[symbol_name].records.itertuples(index=False):
                result[str(record[0])] = kind
        return result


class ConvertDictionaryReader:
    """Read a Convert DictMap GDX and recover semantic scalar names."""

    def __init__(self, system_directory: Path | None = None) -> None:
        self.system_directory = system_directory

    def read(self, path: Path) -> SemanticNameDictionary:
        try:
            import gams.transfer as gt  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError(
                "GDX dictionary reading requires the uv oracle dependency group"
            ) from error
        container = gt.Container(
            system_directory=(
                str(self.system_directory)
                if self.system_directory is not None
                else None
            )
        )
        container.read(str(path))
        rows: list[tuple[str, str]] = []
        columns: list[tuple[str, str]] = []
        for symbol_name in container.listSymbols():
            if not symbol_name.endswith(("_EM", "_VM")):
                continue
            records = container[symbol_name].records
            if records is None:
                continue
            mapping = self.mapping_records(
                symbol_name,
                tuple(
                    tuple(str(value) for value in record[:-1])
                    for record in records.itertuples(index=False, name=None)
                ),
            )
            (rows if symbol_name.endswith("_EM") else columns).extend(mapping)
        if not rows or not columns:
            raise ValueError("Convert dictionary has no equation or variable mappings")
        return SemanticNameDictionary.build(rows, columns)

    @staticmethod
    def mapping_records(
        symbol_name: str,
        records: Sequence[tuple[str, ...]],
    ) -> tuple[tuple[str, str], ...]:
        """Translate one DictMap symbol; exposed for dependency-free TDD."""

        if not symbol_name.endswith(("_EM", "_VM")):
            raise ValueError(f"unsupported Convert mapping symbol: {symbol_name!r}")
        base_name = symbol_name[:-3]
        result: list[tuple[str, str]] = []
        for record in records:
            if not record or not record[0]:
                raise ValueError(f"empty scalar name in {symbol_name}")
            indices = record[1:]
            semantic_name = base_name
            if indices:
                encoded = ",".join(
                    json.dumps(index, ensure_ascii=False, separators=(",", ":"))
                    for index in indices
                )
                semantic_name = f"{base_name}[{encoded}]"
            result.append((record[0], semantic_name))
        return tuple(result)


def _canonical_dataclass(value: Any) -> dict[str, Any]:
    return {key: canonical_value(item) for key, item in asdict(value).items()}


def _bound_violation(value: float, lower: float, upper: float) -> float:
    return max(0.0, lower - value, value - upper)
