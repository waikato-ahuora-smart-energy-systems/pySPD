"""Compare the Pyomo HVDC matrix with the pinned vSPD Stage 6 projection."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyomo.environ as pyo
from pyomo.repn.standard_repn import generate_standard_repn

from pyspd.architecture import ModelAssembler
from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import GdxAdapter
from pyspd.hvdc import hvdc_formulation
from tools.gate5.oracle_matrix import _differences, _source, _summary
from tools.oracle.canonical import (
    ConvertDictionaryReader,
    ConvertMatrixReader,
    LinearMatrixEvidence,
    MatrixColumn,
    MatrixEntry,
    MatrixRow,
)

ROW_FAMILIES = frozenset(
    {
        "HVDClinkMaximumFlow",
        "HVDClinkLossDefinition",
        "HVDClinkFlowDefinition",
        "LambdaDefinition",
    }
)
VARIABLE_FAMILIES = frozenset({"HVDCLINKFLOW", "HVDCLINKLOSSES", "LAMBDA"})
PYOMO_ROWS = {
    "HVDCTransmission.HVDCLinkMaximumFlow": "HVDClinkMaximumFlow",
    "HVDCTransmission.HVDCLinkLossDefinition": "HVDClinkLossDefinition",
    "HVDCTransmission.HVDCLinkFlowDefinition": "HVDClinkFlowDefinition",
    "HVDCTransmission.LambdaDefinition": "LambdaDefinition",
}
PYOMO_VARIABLES = {
    "HVDCTransmission.HVDCLinkFlow": "HVDCLINKFLOW",
    "HVDCTransmission.HVDCLinkLosses": "HVDCLINKLOSSES",
    "HVDCTransmission.Lambda": "LAMBDA",
}


def _semantic(family: str, index: Any) -> str:
    values = index if isinstance(index, tuple) else (index,)
    return f"{family}[{','.join(json.dumps(str(value)) for value in values)}]"


def _canonical(value: float) -> float:
    if value == 0.0:
        return 0.0
    return value if not math.isfinite(value) else round(value, 12)


def _bound(value: Any, default: float) -> float:
    return default if value is None else float(pyo.value(value))


def pyomo_stage6_projection(model: pyo.ConcreteModel) -> LinearMatrixEvidence:
    variable_by_id: dict[int, str] = {}
    columns: list[MatrixColumn] = []
    for variable in model.component_data_objects(pyo.Var, active=True):
        family = PYOMO_VARIABLES.get(variable.parent_component().name)
        if family is None:
            continue
        name = _semantic(family, variable.index())
        variable_by_id[id(variable)] = name
        columns.append(
            MatrixColumn(
                name,
                _canonical(_bound(variable.lb, -math.inf)),
                _canonical(_bound(variable.ub, math.inf)),
                0.0,
                0.0,
                0.0,
                "continuous",
            )
        )
    rows: list[MatrixRow] = []
    entries: list[MatrixEntry] = []
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        family = PYOMO_ROWS.get(constraint.parent_component().name)
        if family is None:
            continue
        name = _semantic(family, constraint.index())
        repn = generate_standard_repn(constraint.body, compute_values=True)
        constant = float(repn.constant or 0.0)
        rows.append(
            MatrixRow(
                name,
                _canonical(_bound(constraint.lower, -math.inf) - constant),
                _canonical(_bound(constraint.upper, math.inf) - constant),
                0.0,
                0.0,
            )
        )
        for variable, coefficient in zip(
            repn.linear_vars, repn.linear_coefs, strict=True
        ):
            column = variable_by_id.get(id(variable))
            if column is not None and float(coefficient) != 0.0:
                entries.append(
                    MatrixEntry(name, column, _canonical(float(coefficient)))
                )
    return LinearMatrixEvidence.build(rows, columns, entries, "maximize")


def gams_stage6_projection(matrix: LinearMatrixEvidence) -> LinearMatrixEvidence:
    rows = tuple(
        MatrixRow(
            row.name,
            _canonical(row.lower),
            _canonical(row.upper),
            0.0,
            0.0,
        )
        for row in matrix.rows
        if row.name.split("[", 1)[0] in ROW_FAMILIES
    )
    columns = tuple(
        MatrixColumn(
            column.name,
            _canonical(column.lower),
            _canonical(column.upper),
            _canonical(column.objective),
            0.0,
            0.0,
            column.discrete_type,
        )
        for column in matrix.columns
        if column.name.split("[", 1)[0] in VARIABLE_FAMILIES
    )
    row_names = {row.name for row in rows}
    column_names = {column.name for column in columns}
    entries = tuple(
        MatrixEntry(entry.row, entry.column, _canonical(entry.coefficient))
        for entry in matrix.entries
        if entry.row in row_names and entry.column in column_names
    )
    return LinearMatrixEvidence.build(rows, columns, entries, matrix.sense)


def compare(
    *,
    input_gdx: Path,
    matrix_gdx: Path,
    dictionary_gdx: Path,
    system_directory: Path,
    identifier: CaseIdentifier,
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    built = ModelAssembler().assemble(
        hvdc_formulation(preprocess=True),
        CaseData("vspd-v5.0.6", identifier, raw),
    )
    python = pyomo_stage6_projection(built.model)
    scalar = ConvertMatrixReader(system_directory).read(matrix_gdx)
    dictionary = ConvertDictionaryReader(system_directory).read(dictionary_gdx)
    gams = gams_stage6_projection(dictionary.apply(scalar))
    differences = _differences(python, gams, tolerance)
    return {
        "schema_version": 1,
        "profile": "vspd-v5.0.6-hvdc-stage6",
        "case": asdict(identifier),
        "sources": {
            "input_gdx": _source(input_gdx),
            "matrix_gdx": _source(matrix_gdx),
            "dictionary_gdx": _source(dictionary_gdx),
        },
        "precision_rule": {
            "absolute_tolerance": tolerance,
            "canonical_decimal_places": 12,
        },
        "python": _summary(python),
        "gams": _summary(gams),
        "differences": differences,
        "passed": all(value == 0 for value in differences.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-gdx", type=Path, required=True)
    parser.add_argument("--matrix-gdx", type=Path, required=True)
    parser.add_argument("--dictionary-gdx", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--datetime", required=True)
    parser.add_argument("--trading-period", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(
        input_gdx=args.input_gdx.resolve(),
        matrix_gdx=args.matrix_gdx.resolve(),
        dictionary_gdx=args.dictionary_gdx.resolve(),
        system_directory=args.system_directory.resolve(),
        identifier=CaseIdentifier(args.case_id, args.datetime, args.trading_period),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
