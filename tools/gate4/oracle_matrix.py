"""Compare the Pyomo core matrix with the approved Gate 1 Stage 4 projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyomo.environ as pyo
from pyomo.repn.standard_repn import generate_standard_repn

from pyspd.architecture import ModelAssembler
from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.core_energy import core_energy_formulation
from pyspd.data import GdxAdapter
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
        "GenerationOfferDefintion",
        "EnergyScarcityDefinition",
        "GenerationRampUp",
        "GenerationRampDown",
        "GenerationChangeUpDown",
        "SystemCostDefinition",
        "SystemBenefitDefinition",
        "SystemPenaltyCostDefinition",
        "TotalViolationCostDefinition",
        "TotalScarcityCostDefinition",
    }
)
VARIABLE_FAMILIES = frozenset(
    {
        "SYSTEMBENEFIT",
        "SYSTEMCOST",
        "SYSTEMPENALTYCOST",
        "TOTALPENALTYCOST",
        "SCARCITYCOST",
        "ENERGYSCARCITYBLK",
        "ENERGYSCARCITYNODE",
        "GENERATION",
        "GENERATIONBLOCK",
        "GENERATIONUPDELTA",
        "GENERATIONDNDELTA",
        "DEFICITRAMPRATE",
        "SURPLUSRAMPRATE",
    }
)

PYOMO_ROWS = {
    "EnergyOffers.GenerationOfferDefinition": "GenerationOfferDefintion",
    "EnergyScarcity.EnergyScarcityDefinition": "EnergyScarcityDefinition",
    "GenerationRamping.RampUp": "GenerationRampUp",
    "GenerationRamping.RampDown": "GenerationRampDown",
    "GenerationRamping.GenerationChange": "GenerationChangeUpDown",
    "Economics.SystemCostDefinition": "SystemCostDefinition",
    "Economics.SystemBenefitDefinition": "SystemBenefitDefinition",
    "Economics.SystemPenaltyDefinition": "SystemPenaltyCostDefinition",
    "Economics.TotalViolationCostDefinition": "TotalViolationCostDefinition",
    "Economics.TotalScarcityCostDefinition": "TotalScarcityCostDefinition",
}
PYOMO_VARIABLES = {
    "Economics.SystemBenefitByPeriod": "SYSTEMBENEFIT",
    "Economics.SystemCostByPeriod": "SYSTEMCOST",
    "Economics.SystemPenaltyByPeriod": "SYSTEMPENALTYCOST",
    "Economics.TotalPenaltyCost": "TOTALPENALTYCOST",
    "Economics.ScarcityCostByPeriod": "SCARCITYCOST",
    "EnergyScarcity.EnergyScarcityBlock": "ENERGYSCARCITYBLK",
    "EnergyScarcity.EnergyScarcityNode": "ENERGYSCARCITYNODE",
    "EnergyOffers.Generation": "GENERATION",
    "EnergyOffers.GenerationBlock": "GENERATIONBLOCK",
    "GenerationRamping.GenerationUpDelta": "GENERATIONUPDELTA",
    "GenerationRamping.GenerationDownDelta": "GENERATIONDNDELTA",
    "GenerationRamping.DeficitRampRate": "DEFICITRAMPRATE",
    "GenerationRamping.SurplusRampRate": "SURPLUSRAMPRATE",
}


def _semantic(family: str, index: Any) -> str:
    if index is None:
        return family
    values = index if isinstance(index, tuple) else (index,)
    return f"{family}[{','.join(json.dumps(str(value)) for value in values)}]"


def pyomo_stage4_projection(model: pyo.ConcreteModel) -> LinearMatrixEvidence:
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


def gams_stage4_projection(matrix: LinearMatrixEvidence) -> LinearMatrixEvidence:
    rows = tuple(
        MatrixRow(
            row.name,
            _zero(row.lower),
            _zero(row.upper),
            _zero(row.marginal),
            None if row.level is None else _zero(row.level),
        )
        for row in matrix.rows
        if _family(row.name) in ROW_FAMILIES
    )
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
    )
    row_names = {row.name for row in rows}
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
) -> dict[str, Any]:
    raw = GdxAdapter.read(input_gdx, system_directory=system_directory)
    built = ModelAssembler().assemble(
        core_energy_formulation(preprocess=True),
        CaseData("vspd-v5.0.6", identifier, raw),
    )
    python = pyomo_stage4_projection(built.model)
    scalar = ConvertMatrixReader(system_directory).read(matrix_gdx)
    dictionary = ConvertDictionaryReader(system_directory).read(dictionary_gdx)
    gams = gams_stage4_projection(dictionary.apply(scalar))
    differences = _differences(python, gams, tolerance)
    return {
        "schema_version": 1,
        "profile": "vspd-v5.0.6-core-energy-stage4",
        "case": asdict(identifier),
        "sources": {
            "input_gdx": _source(input_gdx),
            "matrix_gdx": _source(matrix_gdx),
            "dictionary_gdx": _source(dictionary_gdx),
        },
        "precision_rule": {"absolute_tolerance": tolerance},
        "python": _summary(python),
        "gams": _summary(gams),
        "differences": differences,
        "passed": all(value == 0 for value in differences.values()),
    }


def _differences(
    python: LinearMatrixEvidence, gams: LinearMatrixEvidence, tolerance: float
) -> dict[str, int]:
    python_rows = {row.name: row for row in python.rows}
    gams_rows = {row.name: row for row in gams.rows}
    python_columns = {column.name: column for column in python.columns}
    gams_columns = {column.name: column for column in gams.columns}
    python_entries = {(entry.row, entry.column): entry.coefficient for entry in python.entries}
    gams_entries = {(entry.row, entry.column): entry.coefficient for entry in gams.entries}
    return {
        "missing_rows": len(set(gams_rows) - set(python_rows)),
        "extra_rows": len(set(python_rows) - set(gams_rows)),
        "row_bound_mismatches": _record_mismatches(
            python_rows, gams_rows, ("lower", "upper"), tolerance
        ),
        "missing_columns": len(set(gams_columns) - set(python_columns)),
        "extra_columns": len(set(python_columns) - set(gams_columns)),
        "column_mismatches": _record_mismatches(
            python_columns,
            gams_columns,
            ("lower", "upper", "objective", "discrete_type"),
            tolerance,
        ),
        "missing_nonzeros": len(set(gams_entries) - set(python_entries)),
        "extra_nonzeros": len(set(python_entries) - set(gams_entries)),
        "coefficient_mismatches": sum(
            not _equal(python_entries[key], gams_entries[key], tolerance)
            for key in set(python_entries) & set(gams_entries)
        ),
    }


def _record_mismatches(
    left: dict[str, Any],
    right: dict[str, Any],
    fields: tuple[str, ...],
    tolerance: float,
) -> int:
    return sum(
        any(
            not _equal(getattr(left[name], field), getattr(right[name], field), tolerance)
            for field in fields
        )
        for name in set(left) & set(right)
    )


def _equal(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, str) or isinstance(right, str):
        return left == right
    if math.isinf(float(left)) or math.isinf(float(right)):
        return left == right
    return abs(float(left) - float(right)) <= tolerance


def _bound(value: Any, default: float) -> float:
    return default if value is None else float(pyo.value(value))


def _zero(value: float) -> float:
    return 0.0 if value == 0.0 else value


def _family(name: str) -> str:
    return name.split("[", 1)[0]


def _summary(matrix: LinearMatrixEvidence) -> dict[str, Any]:
    return {
        "sense": matrix.sense,
        "row_count": len(matrix.rows),
        "column_count": len(matrix.columns),
        "nonzero_count": matrix.nonzero_count,
        "structural_sha256": matrix.structural_sha256,
        "logical_sha256": matrix.logical_sha256,
    }


def _source(path: Path) -> dict[str, str]:
    return {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


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
