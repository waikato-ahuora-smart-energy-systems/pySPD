"""Capability-aware continuous-LP solver backend contracts."""

from __future__ import annotations

from collections.abc import Mapping
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

    def solve(
        self,
        model: pyo.ConcreteModel,
        configuration: SolverConfiguration = DEFAULT_SOLVER_CONFIGURATION,
        *,
        load_solution: bool = True,
        accept_nonoptimal: bool = False,
    ) -> SolveResult:
        solver = pyo.SolverFactory("appsi_highs")
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
        loaded = False
        if status is SolveStatus.OPTIMAL and load_solution:
            model.solutions.load_from(raw_results)
            loaded = True
        elif status is not SolveStatus.OPTIMAL and not accept_nonoptimal:
            raise SolverExecutionError(
                f"HiGHS returned {status.value}: solver={raw_status}, "
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
