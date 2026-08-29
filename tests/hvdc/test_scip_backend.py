from __future__ import annotations

import pyomo.environ as pyo
import pytest
from pyomo.opt import SolverResults, SolverStatus, TerminationCondition

from pyspd.solver import (
    GamsScipBackend,
    SolverConfiguration,
    SolverExecutionError,
    SolveStatus,
)


def binary_model() -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model.x = pyo.Var(domain=pyo.Binary)
    model.objective = pyo.Objective(expr=model.x, sense=pyo.maximize)
    return model


class FakeGamsSolver:
    def __init__(
        self,
        *,
        termination: TerminationCondition = TerminationCondition.optimal,
        incumbent: bool = False,
        available: bool = True,
        raises: str | None = None,
    ) -> None:
        self.termination = termination
        self.incumbent = incumbent
        self._available = available
        self.raises = raises
        self.add_options: list[str] = []

    def available(self, exception_flag: bool = False) -> bool:
        return self._available

    def solve(self, _model, **kwargs) -> SolverResults:
        if self.raises is not None:
            raise RuntimeError(self.raises)
        self.add_options = kwargs["add_options"]
        results = SolverResults()
        results.solver.status = SolverStatus.ok
        results.solver.termination_condition = self.termination
        problem = results.problem.add()
        problem.lower_bound = 9.0
        problem.upper_bound = 10.0
        if self.incumbent:
            results.solution.add()
        return results


def test_scip_unavailable_bad_licence_and_optimal_without_incumbent_fail_closed() -> None:
    model = binary_model()
    unavailable = FakeGamsSolver(available=False)
    with pytest.raises(SolverExecutionError, match="unavailable"):
        GamsScipBackend(solver_factory=lambda _name: unavailable).solve_mip(model)
    bad_licence = FakeGamsSolver(raises="licence checkout failed")
    with pytest.raises(SolverExecutionError, match="licence checkout failed"):
        GamsScipBackend(solver_factory=lambda _name: bad_licence).solve_mip(model)
    no_solution = FakeGamsSolver()
    with pytest.raises(SolverExecutionError, match="incumbent=False"):
        GamsScipBackend(solver_factory=lambda _name: no_solution).solve_mip(model)


@pytest.mark.parametrize(
    ("termination", "status"),
    [
        (TerminationCondition.infeasible, SolveStatus.INFEASIBLE),
        (
            TerminationCondition.infeasibleOrUnbounded,
            SolveStatus.INFEASIBLE_OR_UNBOUNDED,
        ),
        (TerminationCondition.unbounded, SolveStatus.UNBOUNDED),
    ],
)
def test_scip_rejected_states_preserve_normalized_distinctions(
    termination, status
) -> None:
    solver = FakeGamsSolver(termination=termination)
    with pytest.raises(SolverExecutionError, match=f"termination={termination}"):
        GamsScipBackend(solver_factory=lambda _name: solver).solve_mip(
            binary_model(), load_solution=False
        )
    assert GamsScipBackend._normalize_status(termination) is status
    assert GamsScipBackend(
        system_directory="/Library/Frameworks/GAMS.framework/Versions/54/Resources"
    )._version() == (54,)


def test_default_backend_prefers_uv_managed_gams_runtime() -> None:
    backend = GamsScipBackend()
    assert backend.system_directory.endswith("site-packages/gamspy_base")
    assert (backend._version()[:1]) == (54,)


def test_timeout_incumbent_is_explicit_and_options_are_forwarded() -> None:
    solver = FakeGamsSolver(
        termination=TerminationCondition.maxTimeLimit, incumbent=True
    )
    configuration = SolverConfiguration(
        {"time_limit_seconds": 0.01, "relative_gap": 0.05}
    )
    result = GamsScipBackend(solver_factory=lambda _name: solver).solve_mip(
        binary_model(),
        configuration,
        load_solution=False,
        accept_nonoptimal_incumbent=True,
    )
    assert result.solve.status is SolveStatus.LIMIT
    assert result.has_incumbent is True
    assert result.solve.solution_loaded is False
    assert result.relative_gap == pytest.approx(0.1)
    assert solver.add_options == ["option reslim=0.01;", "option optcr=0.05;"]


def test_timeout_without_incumbent_is_rejected_even_when_limits_are_accepted() -> None:
    solver = FakeGamsSolver(termination=TerminationCondition.maxTimeLimit)
    with pytest.raises(SolverExecutionError, match="incumbent=False"):
        GamsScipBackend(solver_factory=lambda _name: solver).solve_mip(
            binary_model(), accept_nonoptimal_incumbent=True
        )


def test_optimal_incumbent_reports_bound_gap_and_discrete_count() -> None:
    solver = FakeGamsSolver(incumbent=True)
    result = GamsScipBackend(solver_factory=lambda _name: solver).solve_mip(
        binary_model(), load_solution=False
    )
    assert result.solve.status is SolveStatus.OPTIMAL
    assert result.has_incumbent is True
    assert result.incumbent_objective == 10.0
    assert result.best_bound == 9.0
    assert result.relative_gap == pytest.approx(0.1)
    assert result.discrete_variable_count == 1
