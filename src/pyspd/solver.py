"""Capability-aware continuous-LP solver backend contracts."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo
from pyomo.contrib.solver.common.base import Availability
from pyomo.contrib.solver.common.results import (
    SolutionStatus as DirectSolutionStatus,
)
from pyomo.contrib.solver.common.results import (
    TerminationCondition as DirectTerminationCondition,
)
from pyomo.contrib.solver.solvers.scip.scip_direct import ScipDirect
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

_SYSTEM_GAMS_DIRECTORY = "/Library/Frameworks/GAMS.framework/Versions/54/Resources"


def _default_gams_system_directory() -> str:
    """Prefer the uv-managed GAMS runtime when the optional oracle group exists."""
    specification = find_spec("gamspy_base")
    if specification is not None and specification.submodule_search_locations:
        candidate = Path(next(iter(specification.submodule_search_locations)))
        if (candidate / "gams").is_file():
            return str(candidate)
    return _SYSTEM_GAMS_DIRECTORY


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
        warm_start: bool = False,
    ) -> SolveResult:
        solver = self._solver_factory("appsi_highs")
        if solver is None or not solver.available(exception_flag=False):
            raise SolverExecutionError(
                "HiGHS is unavailable; install the uv 'highs' dependency group"
            )
        for name, value in configuration.options.items():
            solver.options[name] = value
        solve_options: dict[str, Any] = {"load_solutions": False}
        if warm_start:
            solve_options["warmstart"] = True
        try:
            raw_results = solver.solve(model, **solve_options)
        except Exception as error:
            raise SolverExecutionError(f"HiGHS execution error: {error}") from error
        finally:
            if warm_start and hasattr(solver, "config"):
                # The legacy APPSI facade mutates its shared configuration when
                # keyword overrides are supplied. Restore the cold default so
                # a warm solve cannot contaminate later independent solves.
                solver.config.warmstart = False

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
        system_directory: str | None = None,
        solver_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.system_directory = system_directory or _default_gams_system_directory()
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
        if name.isdigit():
            return (int(name),)
        try:
            return tuple(int(part) for part in version("gamspy-base").split("."))
        except (PackageNotFoundError, ValueError):
            return ()

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


class NativeScipBackend(SolverBackend):
    """Native PySCIPOpt primary-MIP backend with no GAMS licence dependency."""

    name = "native-scip"
    interface = "pyomo.contrib.solver.solvers.scip.scip_direct"

    def __init__(self, solver_factory: Callable[[], Any] | None = None) -> None:
        self._solver_factory = solver_factory or ScipDirect

    def solve_mip(
        self,
        model: pyo.ConcreteModel,
        configuration: SolverConfiguration = DEFAULT_SOLVER_CONFIGURATION,
        *,
        load_solution: bool = True,
        accept_nonoptimal_incumbent: bool = False,
        warm_start_discrete: bool = False,
    ) -> MipSolveResult:
        discrete_count = sum(
            variable.is_binary() or variable.is_integer()
            for variable in model.component_data_objects(pyo.Var, active=True)
            if not variable.fixed
        )
        solver = self._solver_factory()
        availability = solver.available()
        if availability is Availability.NotFound or not bool(availability):
            raise SolverExecutionError(
                "native SCIP is unavailable; install PySCIPOpt with uv"
            )
        options = dict(configuration.options)
        known = {"time_limit_seconds", "relative_gap", "absolute_gap", "threads"}
        solve_options: dict[str, Any] = {
            "load_solutions": False,
            "solver_options": {
                name: value for name, value in options.items() if name not in known
            },
        }
        if warm_start_discrete:
            solve_options["warmstart_discrete_vars"] = True
        if "time_limit_seconds" in options:
            solve_options["time_limit"] = float(options["time_limit_seconds"])
        if "relative_gap" in options:
            solve_options["rel_gap"] = float(options["relative_gap"])
        if "absolute_gap" in options:
            solve_options["abs_gap"] = float(options["absolute_gap"])
        if "threads" in options:
            solve_options["threads"] = int(options["threads"])
        try:
            raw_results = solver.solve(model, **solve_options)
        except Exception as error:
            raise SolverExecutionError(
                f"native SCIP execution error: {error}"
            ) from error
        status = self._normalize_status(
            raw_results.termination_condition,
            raw_results.solution_status,
        )
        has_incumbent = raw_results.solution_status in {
            DirectSolutionStatus.optimal,
            DirectSolutionStatus.feasible,
        }
        accepted = (status is SolveStatus.OPTIMAL and has_incumbent) or (
            accept_nonoptimal_incumbent and has_incumbent
        )
        loaded = False
        if accepted and load_solution:
            raw_results.solution_loader.load_vars()
            loaded = True
        elif not accepted:
            raise SolverExecutionError(
                "native SCIP returned a rejected state: "
                f"status={raw_results.solution_status}, "
                f"termination={raw_results.termination_condition}, "
                f"incumbent={has_incumbent}"
            )
        incumbent = _finite_or_none(raw_results.incumbent_objective)
        bound = _finite_or_none(raw_results.objective_bound)
        gap = None
        if incumbent is not None and bound is not None:
            gap = abs(incumbent - bound) / max(1.0, abs(incumbent))
        result = SolveResult(
            backend=self.name,
            interface=self.interface,
            version=tuple(int(part) for part in solver.version()),
            status=status,
            raw_solver_status=str(raw_results.solution_status),
            raw_termination_condition=str(raw_results.termination_condition),
            options=configuration.options,
            solution_loaded=loaded,
            raw_results=raw_results,
        )
        return MipSolveResult(
            result,
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

    @staticmethod
    def _normalize_status(
        termination: Any,
        solution_status: Any,
    ) -> SolveStatus:
        if (
            termination is DirectTerminationCondition.convergenceCriteriaSatisfied
            and solution_status is DirectSolutionStatus.optimal
        ):
            return SolveStatus.OPTIMAL
        if termination is DirectTerminationCondition.provenInfeasible:
            return SolveStatus.INFEASIBLE
        if termination is DirectTerminationCondition.unbounded:
            return SolveStatus.UNBOUNDED
        if termination is DirectTerminationCondition.infeasibleOrUnbounded:
            return SolveStatus.INFEASIBLE_OR_UNBOUNDED
        if termination in {
            DirectTerminationCondition.maxTimeLimit,
            DirectTerminationCondition.iterationLimit,
            DirectTerminationCondition.interrupted,
        }:
            return SolveStatus.LIMIT
        if solution_status is DirectSolutionStatus.noSolution:
            return SolveStatus.NO_SOLUTION
        return SolveStatus.UNKNOWN


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
