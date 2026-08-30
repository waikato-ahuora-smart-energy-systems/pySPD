"""Native SCIP backend tests for the portable primary-MIP path."""

from __future__ import annotations

import pyomo.environ as pyo
import pytest

from pyspd.solver import (
    NativeScipBackend,
    SolverConfiguration,
    SolverExecutionError,
    SolveStatus,
)


def _binary_model() -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model.x = pyo.Var(domain=pyo.Binary)
    model.y = pyo.Var(domain=pyo.NonNegativeReals, bounds=(0.0, 2.0))
    model.capacity = pyo.Constraint(expr=model.y <= 2.0 * model.x)
    model.objective = pyo.Objective(expr=3.0 * model.y - model.x, sense=pyo.maximize)
    return model


def test_native_scip_solves_and_loads_an_optimal_mip() -> None:
    model = _binary_model()

    outcome = NativeScipBackend().solve_mip(
        model,
        SolverConfiguration(
            {
                "time_limit_seconds": 10.0,
                "relative_gap": 0.0,
                "threads": 1,
            }
        ),
    )

    assert outcome.solve.backend == "native-scip"
    assert outcome.solve.status is SolveStatus.OPTIMAL
    assert outcome.solve.solution_loaded
    assert outcome.has_incumbent
    assert outcome.discrete_variable_count == 1
    assert pyo.value(model.x) == pytest.approx(1.0)
    assert pyo.value(model.y) == pytest.approx(2.0)
    assert outcome.incumbent_objective == pytest.approx(5.0)
    assert outcome.best_bound == pytest.approx(5.0)
    assert outcome.relative_gap == pytest.approx(0.0)


class UnavailableScip:
    def available(self):
        from pyomo.contrib.solver.common.base import Availability

        return Availability.NotFound


def test_native_scip_fails_explicitly_when_runtime_is_unavailable() -> None:
    with pytest.raises(SolverExecutionError, match="install PySCIPOpt with uv"):
        NativeScipBackend(solver_factory=UnavailableScip).solve_mip(_binary_model())
