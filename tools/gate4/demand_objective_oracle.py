"""Certify demand-bid rows and the affine objective constant against GAMS."""

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
from pyspd.contracts import CaseIdentifier
from pyspd.data import GdxAdapter
from pyspd.orchestration import DailyCaseSelector
from pyspd.reserve import reserve_formulation
from tools.gate4.oracle_matrix import (
    _bound,
    _differences,
    _semantic,
    _source,
    _summary,
    _zero,
)
from tools.oracle.canonical import (
    ConvertDictionaryReader,
    ConvertMatrixReader,
    LinearMatrixEvidence,
    MatrixColumn,
    MatrixEntry,
    MatrixRow,
)

ROW_FAMILIES = frozenset({"DemBidDefintion", "DemBidDiscrete"})
VARIABLE_FAMILIES = frozenset(
    {"PURCHASE", "PURCHASEBLOCK", "PURCHASEBLOCKBINARY"}
)
PYOMO_ROWS = {
    "DemandBids.DemandBidDefinition": "DemBidDefintion",
    "DiscreteDemand.DemBidDiscrete": "DemBidDiscrete",
}
PYOMO_VARIABLES = {
    "DemandBids.Purchase": "PURCHASE",
    "DemandBids.PurchaseBlock": "PURCHASEBLOCK",
    "DiscreteDemand.PurchaseBlockBinary": "PURCHASEBLOCKBINARY",
}


def pyomo_demand_projection(model: pyo.ConcreteModel) -> LinearMatrixEvidence:
    objective = next(model.component_data_objects(pyo.Objective, active=True))
    objective_repn = generate_standard_repn(objective.expr, compute_values=True)
    objective_by_id = {
        id(variable): float(coefficient)
        for variable, coefficient in zip(
            objective_repn.linear_vars, objective_repn.linear_coefs, strict=True
        )
    }
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
                _bound(variable.lb, -math.inf),
                _bound(variable.ub, math.inf),
                objective_by_id.get(id(variable), 0.0),
                0.0,
                0.0,
                "binary"
                if variable.is_binary()
                else "integer"
                if variable.is_integer()
                else "continuous",
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
                _bound(constraint.lower, -math.inf) - constant,
                _bound(constraint.upper, math.inf) - constant,
                0.0,
                0.0,
            )
        )
        for variable, coefficient in zip(
            repn.linear_vars, repn.linear_coefs, strict=True
        ):
            column = variable_by_id.get(id(variable))
            if column is not None and float(coefficient) != 0.0:
                entries.append(MatrixEntry(name, column, float(coefficient)))
    return LinearMatrixEvidence.build(rows, columns, entries, "maximize")


def gams_demand_projection(matrix: LinearMatrixEvidence) -> LinearMatrixEvidence:
    active_discrete_rows = {
        entry.row
        for entry in matrix.entries
        if _family(entry.row) == "DemBidDiscrete"
        and _family(entry.column) == "PURCHASEBLOCKBINARY"
        and entry.coefficient != 0.0
    }
    rows = tuple(
        MatrixRow(
            row.name,
            _zero(row.lower),
            _zero(row.upper),
            _zero(row.marginal),
            None if row.level is None else _zero(row.level),
        )
        for row in matrix.rows
        if _family(row.name) == "DemBidDefintion"
        or row.name in active_discrete_rows
    )
    row_names = {row.name for row in rows}
    referenced_columns = {
        entry.column for entry in matrix.entries if entry.row in row_names
    }
    columns = tuple(
        MatrixColumn(
            column.name,
            _zero(column.lower),
            _zero(column.upper),
            _zero(column.objective),
            _zero(column.level),
            _zero(column.reduced_cost),
            column.discrete_type,
        )
        for column in matrix.columns
        if _family(column.name) in VARIABLE_FAMILIES
        and column.name in referenced_columns
    )
    column_names = {column.name for column in columns}
    entries = tuple(
        MatrixEntry(entry.row, entry.column, _zero(entry.coefficient))
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
    objective_tolerance: float = 1e-7,
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    selector = DailyCaseSelector()
    selected = selector.select(raw, case_ids=(identifier.case_id,))
    if len(selected) != 1 or (
        selected[0].date_time,
        selected[0].trading_period,
    ) != (identifier.date_time, identifier.trading_period):
        raise ValueError("selected GDX case does not match the oracle identifier")
    built = ModelAssembler().assemble(
        reserve_formulation(preprocess=True),
        selector.case_data(raw, selected[0]),
    )
    python = pyomo_demand_projection(built.model)
    reader = ConvertMatrixReader(system_directory)
    scalar = reader.read(matrix_gdx)
    dictionary = ConvertDictionaryReader(system_directory).read(dictionary_gdx)
    semantic = dictionary.apply(scalar)
    gams = gams_demand_projection(semantic)
    differences = _differences(python, gams, tolerance)
    objective = next(
        built.model.component_data_objects(pyo.Objective, active=True)
    )
    python_constant = float(
        generate_standard_repn(objective.expr, compute_values=True).constant or 0.0
    )
    gams_definition = reader.read_objective_definition(matrix_gdx)
    constant_difference = abs(python_constant - gams_definition.constant)
    coverage = {
        family: {
            "gams_rows": sum(_family(row.name) == family for row in gams.rows),
            "python_rows": sum(_family(row.name) == family for row in python.rows),
        }
        for family in sorted(ROW_FAMILIES)
    }
    all_gams_discrete_rows = sum(
        _family(row.name) == "DemBidDiscrete"
        for row in semantic.rows
    )
    rows_covered = all(
        counts["gams_rows"] > 0 and counts["gams_rows"] == counts["python_rows"]
        for counts in coverage.values()
    )
    constant_passed = (
        gams_definition.sense == "maximize"
        and constant_difference <= objective_tolerance
    )
    passed = (
        all(value == 0 for value in differences.values())
        and rows_covered
        and constant_passed
    )
    return {
        "schema_version": 1,
        "profile": "vspd-v5.0.6-demand-objective-oracle",
        "case": asdict(identifier),
        "sources": {
            "input_gdx": _source(input_gdx),
            "matrix_gdx": _source(matrix_gdx),
            "dictionary_gdx": _source(dictionary_gdx),
        },
        "precision_rule": {
            "matrix_absolute_tolerance": tolerance,
            "objective_constant_absolute_tolerance_nzd": objective_tolerance,
        },
        "coverage": coverage,
        "projection": {
            "gams_zero_mw_discrete_rows_excluded": (
                all_gams_discrete_rows - coverage["DemBidDiscrete"]["gams_rows"]
            ),
            "reason": (
                "GAMS expands a discrete bid across all global block labels; "
                "rows with zero bid MW only restate an already fixed zero "
                "PURCHASEBLOCK and leave an economically inert binary."
            ),
        },
        "python": _summary(python),
        "gams": _summary(gams),
        "differences": differences,
        "objective_constant": {
            "gams_nzd": gams_definition.constant,
            "python_nzd": python_constant,
            "difference_nzd": constant_difference,
            "gams_objective_row": gams_definition.objective_row,
            "gams_objective_column": gams_definition.objective_column,
            "gams_objective_jacobian": gams_definition.objective_jacobian,
            "passed": constant_passed,
        },
        "passed": passed,
    }


def _family(name: str) -> str:
    return name.split("[", 1)[0]


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
    arguments = parser.parse_args()
    report = compare(
        input_gdx=arguments.input_gdx.resolve(),
        matrix_gdx=arguments.matrix_gdx.resolve(),
        dictionary_gdx=arguments.dictionary_gdx.resolve(),
        system_directory=arguments.system_directory.resolve(),
        identifier=CaseIdentifier(
            arguments.case_id, arguments.datetime, arguments.trading_period
        ),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "output": str(arguments.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
