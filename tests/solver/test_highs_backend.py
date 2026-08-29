from __future__ import annotations

import pyomo.environ as pyo
import pytest
from pyomo.opt import SolverResults, SolverStatus, TerminationCondition

from pyspd.solver import (
    HighsBackend,
    SolverConfiguration,
    SolverExecutionError,
    SolveStatus,
)


def optimal_model() -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model.x = pyo.Var(bounds=(0, None))
    model.balance = pyo.Constraint(expr=model.x >= 1)
    model.objective = pyo.Objective(expr=model.x)
    return model


def test_highs_safe_load_and_effective_options() -> None:
    backend = HighsBackend()
    model = optimal_model()
    configuration = SolverConfiguration(
        {"primal_feasibility_tolerance": 1e-8, "solver": "simplex"}
    )

    unloaded = backend.solve(model, configuration, load_solution=False)
    assert unloaded.status is SolveStatus.OPTIMAL
    assert unloaded.solution_loaded is False
    assert model.x.value is None
    assert unloaded.interface == "pyomo.contrib.appsi_highs"
    assert unloaded.version >= (1, 11)
    assert unloaded.options == configuration.options

    loaded = backend.solve(model, configuration)
    assert loaded.solution_loaded is True
    assert model.x.value == pytest.approx(1.0)


def test_nonoptimal_results_are_mapped_but_not_silently_loaded() -> None:
    model = pyo.ConcreteModel()
    model.x = pyo.Var()
    model.low = pyo.Constraint(expr=model.x >= 2)
    model.high = pyo.Constraint(expr=model.x <= 1)
    model.objective = pyo.Objective(expr=model.x)

    with pytest.raises(SolverExecutionError, match="infeasible"):
        HighsBackend().solve(model)
    assert model.x.value is None

    result = HighsBackend().solve(
        model, load_solution=False, accept_nonoptimal=True
    )
    assert result.status is SolveStatus.INFEASIBLE
    assert result.solution_loaded is False


def test_solver_configuration_is_immutable() -> None:
    configuration = SolverConfiguration({"threads": 1})

    with pytest.raises(TypeError):
        configuration.options["threads"] = 2  # type: ignore[index]


class FakeSolver:
    def __init__(self, *, available: bool = True, raises: bool = False) -> None:
        self._available = available
        self._raises = raises
        self.options: dict[str, object] = {}

    def available(self, exception_flag: bool = False) -> bool:
        return self._available

    def version(self) -> tuple[int, ...]:
        return (1, 15, 1)

    def solve(self, model: object, load_solutions: bool = False) -> SolverResults:
        if self._raises:
            raise RuntimeError("synthetic backend failure")
        results = SolverResults()
        results.solver.status = SolverStatus.ok
        results.solver.termination_condition = TerminationCondition.optimal
        return results


def test_unavailable_error_and_optimal_without_solution_fail_closed() -> None:
    model = optimal_model()

    with pytest.raises(SolverExecutionError, match="unavailable"):
        HighsBackend(solver_factory=lambda _name: FakeSolver(available=False)).solve(
            model
        )
    with pytest.raises(SolverExecutionError, match="synthetic backend failure"):
        HighsBackend(solver_factory=lambda _name: FakeSolver(raises=True)).solve(model)
    with pytest.raises(SolverExecutionError, match="optimal.*no solution"):
        HighsBackend(solver_factory=lambda _name: FakeSolver()).solve(model)
    result = HighsBackend(solver_factory=lambda _name: FakeSolver()).solve(
        model, load_solution=False, accept_nonoptimal=True
    )
    assert result.status is SolveStatus.NO_SOLUTION
    assert result.solution_loaded is False


def test_unbounded_and_limit_statuses_are_normalized_without_loading() -> None:
    model = pyo.ConcreteModel()
    model.x = pyo.Var()
    model.objective = pyo.Objective(expr=-model.x)

    result = HighsBackend().solve(
        model, load_solution=False, accept_nonoptimal=True
    )
    assert result.status in {SolveStatus.UNBOUNDED, SolveStatus.INFEASIBLE_OR_UNBOUNDED}
    assert model.x.value is None
    assert (
        HighsBackend._normalize(SolverStatus.ok, TerminationCondition.maxTimeLimit)
        is SolveStatus.LIMIT
    )
