from __future__ import annotations

import pyomo.environ as pyo
import pytest

from pyspd.solver import (
    ClpBackend,
    SolverConfiguration,
    SolverExecutionError,
    SolveStatus,
)


def linear_model() -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model.x = pyo.Var(bounds=(0.0, None))
    model.balance = pyo.Constraint(expr=model.x >= 1.0)
    model.objective = pyo.Objective(expr=model.x)
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
    return model


def test_clp_safely_loads_primal_and_constraint_dual() -> None:
    backend = ClpBackend()
    model = linear_model()
    configuration = SolverConfiguration(
        {
            "primal_feasibility_tolerance": 1e-9,
            "dual_feasibility_tolerance": 1e-9,
            "log_level": 0,
        }
    )

    unloaded = backend.solve(model, configuration, load_solution=False)
    assert unloaded.status is SolveStatus.OPTIMAL
    assert unloaded.solution_loaded is False
    assert model.x.value is None
    assert unloaded.interface == "cylp.cy.CyClpSimplex"

    loaded = backend.solve(model, configuration)
    assert loaded.status is SolveStatus.OPTIMAL
    assert loaded.solution_loaded is True
    assert model.x.value == pytest.approx(1.0)
    assert model.dual[model.balance] == pytest.approx(1.0)


def test_clp_rejects_nonoptimal_and_nonlinear_models() -> None:
    infeasible = pyo.ConcreteModel()
    infeasible.x = pyo.Var()
    infeasible.low = pyo.Constraint(expr=infeasible.x >= 2.0)
    infeasible.high = pyo.Constraint(expr=infeasible.x <= 1.0)
    infeasible.objective = pyo.Objective(expr=infeasible.x)

    with pytest.raises(SolverExecutionError, match="primal infeasible"):
        ClpBackend().solve(infeasible)
    mapped = ClpBackend().solve(infeasible, load_solution=False, accept_nonoptimal=True)
    assert mapped.status is SolveStatus.INFEASIBLE

    nonlinear = pyo.ConcreteModel()
    nonlinear.x = pyo.Var()
    nonlinear.objective = pyo.Objective(expr=nonlinear.x**2)
    with pytest.raises(SolverExecutionError, match="linear models"):
        ClpBackend().solve(nonlinear)
