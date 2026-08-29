"""Deterministic canonical linear-matrix evidence for Pyomo LP builds."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pyomo.environ as pyo
from pyomo.repn.standard_repn import generate_standard_repn


@dataclass(frozen=True, slots=True)
class CanonicalVariable:
    name: str
    lower: float | None
    upper: float | None
    domain: str
    objective: float


@dataclass(frozen=True, slots=True)
class CanonicalRow:
    name: str
    lower: float | None
    upper: float | None
    coefficients: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class CanonicalLinearMatrix:
    objective_sense: str
    objective_constant: float
    variables: tuple[CanonicalVariable, ...]
    rows: tuple[CanonicalRow, ...]
    logical_sha256: str

    def logical_payload(self) -> dict[str, Any]:
        return {
            "objective_sense": self.objective_sense,
            "objective_constant": self.objective_constant.hex(),
            "variables": [
                {
                    "name": item.name,
                    "lower": None if item.lower is None else item.lower.hex(),
                    "upper": None if item.upper is None else item.upper.hex(),
                    "domain": item.domain,
                    "objective": item.objective.hex(),
                }
                for item in self.variables
            ],
            "rows": [
                {
                    "name": item.name,
                    "lower": None if item.lower is None else item.lower.hex(),
                    "upper": None if item.upper is None else item.upper.hex(),
                    "coefficients": [
                        {"variable": name, "value": value.hex()}
                        for name, value in item.coefficients
                    ],
                }
                for item in self.rows
            ],
        }


def canonical_linear_matrix(model: pyo.ConcreteModel) -> CanonicalLinearMatrix:
    objectives = list(model.component_data_objects(pyo.Objective, active=True))
    if len(objectives) != 1:
        raise ValueError("canonical matrix requires exactly one active objective")
    objective = objectives[0]
    objective_repn = generate_standard_repn(objective.expr, compute_values=True)
    if not objective_repn.is_linear():
        raise ValueError("canonical matrix supports linear objectives only")
    objective_coefficients = {
        variable.name: float(coefficient)
        for variable, coefficient in zip(
            objective_repn.linear_vars, objective_repn.linear_coefs, strict=True
        )
    }
    variables = tuple(
        CanonicalVariable(
            variable.name,
            _value_or_none(variable.lb),
            _value_or_none(variable.ub),
            "continuous" if variable.is_continuous() else "integer",
            objective_coefficients.get(variable.name, 0.0),
        )
        for variable in sorted(
            model.component_data_objects(pyo.Var, active=True), key=lambda item: item.name
        )
    )
    rows: list[CanonicalRow] = []
    for constraint in sorted(
        model.component_data_objects(pyo.Constraint, active=True),
        key=lambda item: item.name,
    ):
        repn = generate_standard_repn(constraint.body, compute_values=True)
        if not repn.is_linear():
            raise ValueError(f"nonlinear constraint: {constraint.name}")
        constant = float(repn.constant or 0.0)
        coefficients = tuple(
            sorted(
                (
                    (variable.name, float(coefficient))
                    for variable, coefficient in zip(
                        repn.linear_vars, repn.linear_coefs, strict=True
                    )
                    if float(coefficient) != 0.0
                ),
                key=lambda item: item[0],
            )
        )
        rows.append(
            CanonicalRow(
                constraint.name,
                None
                if constraint.lower is None
                else float(pyo.value(constraint.lower)) - constant,
                None
                if constraint.upper is None
                else float(pyo.value(constraint.upper)) - constant,
                coefficients,
            )
        )
    temporary = CanonicalLinearMatrix(
        "maximize" if objective.sense == pyo.maximize else "minimize",
        float(objective_repn.constant or 0.0),
        variables,
        tuple(rows),
        "",
    )
    digest = hashlib.sha256(
        json.dumps(
            temporary.logical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return CanonicalLinearMatrix(
        temporary.objective_sense,
        temporary.objective_constant,
        temporary.variables,
        temporary.rows,
        digest,
    )


def _value_or_none(value: Any) -> float | None:
    return None if value is None else float(pyo.value(value))
