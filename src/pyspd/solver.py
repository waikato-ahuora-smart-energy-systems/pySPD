"""Capability-aware continuous-LP solver backend contracts."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo
from pyomo.opt import SolverStatus as PyomoSolverStatus
from pyomo.opt import TerminationCondition


class SolveStatus(StrEnum):
    OPTIMAL = "optimal"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    INFEASIBLE_OR_UNBOUNDED = "infeasible_or_unbounded"
    LIMIT = "limit"
    ERROR = "error"
    UNAVAILABLE = "unavailable"
    NO_SOLUTION = "no_solution"
    UNKNOWN = "unknown"


class SolverExecutionError(RuntimeError):
    """A solver was unavailable or did not return an acceptable solution."""


@dataclass(frozen=True, slots=True)
class SolverConfiguration:
    options: Mapping[str, int | float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


DEFAULT_SOLVER_CONFIGURATION = SolverConfiguration()


@dataclass(frozen=True, slots=True)
class SolveResult:
    backend: str
    interface: str
    version: tuple[int, ...]
    status: SolveStatus
    raw_solver_status: str
    raw_termination_condition: str
    options: Mapping[str, int | float | str]
    solution_loaded: bool
    raw_results: Any = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class MipSolveResult:
    """Capability-aware primary-MIP outcome without erasing raw semantics."""

    solve: SolveResult
    has_incumbent: bool
    incumbent_objective: float | None
    best_bound: float | None
    relative_gap: float | None
    discrete_variable_count: int


class SolverBackend:
    """Base backend contract; implementations never silently load failures."""

    name: str

    def solve(
        self,
        model: pyo.ConcreteModel,
        configuration: SolverConfiguration = DEFAULT_SOLVER_CONFIGURATION,
        *,
        load_solution: bool = True,
        accept_nonoptimal: bool = False,
    ) -> SolveResult:
        raise NotImplementedError


class HighsBackend(SolverBackend):
    name = "highs"
    interface = "pyomo.contrib.appsi_highs"

    def __init__(self, solver_factory: Callable[[str], Any] | None = None) -> None:
        self._solver_factory = solver_factory or pyo.SolverFactory

    def solve(
        self,
        model: pyo.ConcreteModel,
        configuration: SolverConfiguration = DEFAULT_SOLVER_CONFIGURATION,
        *,
        load_solution: bool = True,
        accept_nonoptimal: bool = False,
    ) -> SolveResult:
        solver = self._solver_factory("appsi_highs")
        if solver is None or not solver.available(exception_flag=False):
            raise SolverExecutionError(
                "HiGHS is unavailable; install the uv 'highs' dependency group"
            )
        for name, value in configuration.options.items():
            solver.options[name] = value
        try:
            raw_results = solver.solve(model, load_solutions=False)
        except Exception as error:
            raise SolverExecutionError(f"HiGHS execution error: {error}") from error

        raw_status = raw_results.solver.status
        termination = raw_results.solver.termination_condition
        status = self._normalize(raw_status, termination)
        solution_count = len(getattr(raw_results, "solution", ()))
        if status is SolveStatus.OPTIMAL and solution_count == 0:
            status = SolveStatus.NO_SOLUTION
        loaded = False
        if status is SolveStatus.OPTIMAL and load_solution:
            model.solutions.load_from(raw_results)
            loaded = True
        elif status is not SolveStatus.OPTIMAL and not accept_nonoptimal:
            detail = (
                "optimal status but no solution"
                if status is SolveStatus.NO_SOLUTION
                else status.value
            )
            raise SolverExecutionError(
                f"HiGHS returned {detail}: solver={raw_status}, "
                f"termination={termination}"
            )
        return SolveResult(
            backend=self.name,
            interface=self.interface,
            version=tuple(int(part) for part in solver.version()),
            status=status,
            raw_solver_status=str(raw_status),
            raw_termination_condition=str(termination),
            options=configuration.options,
            solution_loaded=loaded,
            raw_results=raw_results,
        )

    @staticmethod
    def _normalize(raw_status: Any, termination: Any) -> SolveStatus:
        if termination is TerminationCondition.optimal:
            return SolveStatus.OPTIMAL
        if termination is TerminationCondition.infeasible:
            return SolveStatus.INFEASIBLE
        if termination is TerminationCondition.unbounded:
            return SolveStatus.UNBOUNDED
        if termination is TerminationCondition.infeasibleOrUnbounded:
            return SolveStatus.INFEASIBLE_OR_UNBOUNDED
        if termination in {
            TerminationCondition.maxTimeLimit,
            TerminationCondition.maxIterations,
            TerminationCondition.resourceInterrupt,
            TerminationCondition.userInterrupt,
        }:
            return SolveStatus.LIMIT
        if raw_status is PyomoSolverStatus.error:
            return SolveStatus.ERROR
        return SolveStatus.UNKNOWN


class GamsScipBackend(SolverBackend):
    """Licensed GAMS/SCIP primary-MIP backend used by the Gate 6 state machine."""

    name = "gams-scip"
    interface = "pyomo.solvers.plugins.solvers.GAMS.GAMSShell"

    def __init__(
        self,
        system_directory: str = "/Library/Frameworks/GAMS.framework/Versions/54/Resources",
        solver_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.system_directory = system_directory
        self._solver_factory = solver_factory or pyo.SolverFactory

    def solve_mip(
        self,
        model: pyo.ConcreteModel,
        configuration: SolverConfiguration = DEFAULT_SOLVER_CONFIGURATION,
        *,
        load_solution: bool = True,
        accept_nonoptimal_incumbent: bool = False,
    ) -> MipSolveResult:
        discrete_count = sum(
            variable.is_binary() or variable.is_integer()
            for variable in model.component_data_objects(pyo.Var, active=True)
            if not variable.fixed
        )
        previous_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.system_directory}:{previous_path}"
        try:
            solver = self._solver_factory("gams")
            if solver is None or not solver.available(exception_flag=False):
                raise SolverExecutionError(
                    "GAMS shell interface is unavailable for the SCIP primary MIP"
                )
            add_options = self._gams_options(configuration)
            try:
                raw_results = solver.solve(
                    model,
                    solver="scip",
                    load_solutions=False,
                    add_options=add_options,
                )
            except Exception as error:
                raise SolverExecutionError(
                    f"GAMS SCIP execution or licence error: {error}"
                ) from error
        finally:
            os.environ["PATH"] = previous_path

        raw_status = raw_results.solver.status
        termination = raw_results.solver.termination_condition
        status = self._normalize_status(termination, raw_status)
        solution_count = len(getattr(raw_results, "solution", ()))
        has_incumbent = solution_count > 0
        loaded = False
        accepted = (status is SolveStatus.OPTIMAL and has_incumbent) or (
            accept_nonoptimal_incumbent and has_incumbent
        )
        if accepted and load_solution:
            model.solutions.load_from(raw_results)
            loaded = True
        elif not accepted:
            raise SolverExecutionError(
                "GAMS SCIP returned a rejected state: "
                f"status={raw_status}, termination={termination}, "
                f"incumbent={has_incumbent}"
            )
        problem = next(iter(raw_results.problem), None)
        lower = _finite_or_none(getattr(problem, "lower_bound", None))
        upper = _finite_or_none(getattr(problem, "upper_bound", None))
        sense = next(model.component_data_objects(pyo.Objective, active=True)).sense
        incumbent = upper if sense == pyo.maximize else lower
        bound = lower if sense == pyo.maximize else upper
        gap = None
        if incumbent is not None and bound is not None:
            gap = abs(incumbent - bound) / max(1.0, abs(incumbent))
        solve_result = SolveResult(
            backend=self.name,
            interface=self.interface,
            version=self._version(),
            status=status,
            raw_solver_status=str(raw_status),
            raw_termination_condition=str(termination),
            options=configuration.options,
            solution_loaded=loaded,
            raw_results=raw_results,
        )
        return MipSolveResult(
            solve_result,
            has_incumbent,
            incumbent,
            bound,
            gap,
            discrete_count,
        )

    def solve(
        self,
        model: pyo.ConcreteModel,
        configuration: SolverConfiguration = DEFAULT_SOLVER_CONFIGURATION,
        *,
        load_solution: bool = True,
        accept_nonoptimal: bool = False,
    ) -> SolveResult:
        return self.solve_mip(
            model,
            configuration,
            load_solution=load_solution,
            accept_nonoptimal_incumbent=accept_nonoptimal,
        ).solve

    def _version(self) -> tuple[int, ...]:
        name = os.path.basename(
            os.path.dirname(os.path.normpath(self.system_directory))
        )
        return (int(name),) if name.isdigit() else ()

    @staticmethod
    def _normalize_status(
        termination: Any, raw_status: Any = PyomoSolverStatus.ok
    ) -> SolveStatus:
        """Expose the normalized status map for evidence and backend tests."""
        return HighsBackend._normalize(raw_status, termination)

    @staticmethod
    def _gams_options(configuration: SolverConfiguration) -> list[str]:
        statements: list[str] = []
        if "time_limit_seconds" in configuration.options:
            statements.append(
                f"option reslim={float(configuration.options['time_limit_seconds'])};"
            )
        if "relative_gap" in configuration.options:
            statements.append(
                f"option optcr={float(configuration.options['relative_gap'])};"
            )
        if "threads" in configuration.options:
            statements.append(
                f"option threads={int(configuration.options['threads'])};"
            )
        return statements


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
