"""Measure independent trading-period solves against one vectorized Pyomo model.

This is an investigation tool, not a production execution mode.  It deliberately
benchmarks one initial SCIP MIP -> fixed HiGHS RMIP solve per period.  The daily
shortfall-transfer loop remains period-local and is outside this experiment.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any, cast

import pyomo.environ as pyo
from pyomo.repn import generate_standard_repn

from pyspd.application import ApplicationConfiguration, PyspdApplication, _file_sha256
from pyspd.architecture import BuiltModel, ModelAssembler
from pyspd.hvdc.data import SosRepresentation
from pyspd.hvdc.formulation import HvdcSolveOutcome, HvdcSolvePolicy
from pyspd.orchestration.solver import _updated_case
from pyspd.reserve import RESERVE_FORMULATION_ID, ReserveCase, reserve_formulation


class CaseMergeError(ValueError):
    """Independent period cases cannot safely share one model instance."""


def _merge_dataclass_instances[T](values: Sequence[T]) -> T:
    """Recursively union disjoint immutable case data.

    Period-indexed sets and mappings are joined.  Configuration scalars must be
    identical.  The two root provenance fields receive deterministic batch
    values and all mapping collisions fail closed, even when values happen to
    be equal, so an accidental duplicate period cannot be hidden.
    """

    if len(values) < 2:
        raise CaseMergeError("at least two cases are required")
    first = values[0]
    if not is_dataclass(first) or any(
        type(value) is not type(first) for value in values
    ):
        raise CaseMergeError("all merged values must share one dataclass type")

    def merge(items: Sequence[Any], path: tuple[str, ...]) -> Any:
        head = items[0]
        if is_dataclass(head) and not isinstance(head, type):
            value_type = type(head)
            kwargs: dict[str, Any] = {}
            for item in fields(head):
                if not item.init:
                    continue
                children = [getattr(value, item.name) for value in items]
                child_path = (*path, item.name)
                if path == () and item.name == "case_id":
                    kwargs[item.name] = "batch[" + ",".join(children) + "]"
                elif path == () and item.name == "preprocessing_signature":
                    payload = json.dumps(children, separators=(",", ":"))
                    kwargs[item.name] = hashlib.sha256(payload.encode()).hexdigest()
                else:
                    kwargs[item.name] = merge(children, child_path)
            return value_type(**kwargs)
        if isinstance(head, Mapping):
            output: dict[Any, Any] = {}
            for mapping in items:
                overlap = set(output).intersection(mapping)
                if overlap:
                    key = min(overlap, key=repr)
                    raise CaseMergeError(
                        f"conflicting mapping key at {'.'.join(path)}: {key!r}"
                    )
                output.update(mapping)
            return output
        if isinstance(head, frozenset):
            return frozenset().union(*items)
        if isinstance(head, tuple):
            if any(item != head for item in items[1:]):
                raise CaseMergeError(f"configuration tuple differs at {'.'.join(path)}")
            return head
        if any(item != head for item in items[1:]):
            raise CaseMergeError(f"configuration value differs at {'.'.join(path)}")
        return head

    return cast(T, merge(values, ()))


def merge_reserve_cases(cases: Sequence[ReserveCase]) -> ReserveCase:
    """Return a validated multi-period ReserveCase with independent domains."""

    merged = _merge_dataclass_instances(cases)
    if len(merged.periods) != sum(len(case.periods) for case in cases):
        raise CaseMergeError("merged periods are not disjoint")
    return merged


def _take_distinct_trading_periods(
    prepared_cases: Iterable[Any], count: int
) -> tuple[Any, ...]:
    selected: list[Any] = []
    periods: set[str] = set()
    for prepared in prepared_cases:
        period = prepared.specification.trading_period
        if period in periods:
            continue
        periods.add(period)
        selected.append(prepared)
        if len(selected) == count:
            break
    return tuple(selected)


def _model_size(built: BuiltModel) -> dict[str, int]:
    model = built.model
    return {
        "variables": sum(1 for _ in model.component_data_objects(pyo.Var, active=True)),
        "constraints": sum(
            1 for _ in model.component_data_objects(pyo.Constraint, active=True)
        ),
        "objectives": sum(
            1 for _ in model.component_data_objects(pyo.Objective, active=True)
        ),
    }


def _cross_period_constraints(built: BuiltModel) -> list[dict[str, Any]]:
    """Return algebraic rows that contain variables from multiple periods."""

    periods = set(built.case_data.periods)
    mixed: list[dict[str, Any]] = []
    for constraint in built.model.component_data_objects(
        pyo.Constraint, active=True, sort=True
    ):
        representation = generate_standard_repn(constraint.body)
        variable_periods: set[tuple[str, str]] = set()
        for variable in representation.linear_vars:
            index = variable.index()
            if not isinstance(index, tuple) or len(index) < 2:
                continue
            period = (str(index[0]), str(index[1]))
            if period in periods:
                variable_periods.add(period)
        if len(variable_periods) > 1:
            mixed.append(
                {
                    "constraint": constraint.name,
                    "periods": [list(period) for period in sorted(variable_periods)],
                }
            )
    return mixed


_PARITY_SURFACES = (
    "generation",
    "purchase",
    "reserve",
    "island_reserve",
    "directed_branch_flow",
)


def _solution_values(
    outcome: HvdcSolveOutcome,
) -> dict[str, dict[tuple[str, ...], float]]:
    return {
        name: {
            tuple(index): float(pyo.value(component[index], exception=False) or 0.0)
            for index in component
        }
        for name in _PARITY_SURFACES
        for component in (outcome.pricing_model.artifacts[name],)
    }


def _parity_summary(
    *,
    separate_objective: float,
    vectorized_objective: float,
    separate_values: Mapping[str, Mapping[tuple[str, ...], float]],
    vectorized_values: Mapping[str, Mapping[tuple[str, ...], float]],
    tolerance: float,
) -> dict[str, Any]:
    maximum = 0.0
    difference_count = 0
    compared = 0
    surface_maxima: dict[str, float] = {}
    for surface in sorted(set(separate_values) | set(vectorized_values)):
        left = separate_values.get(surface, {})
        right = vectorized_values.get(surface, {})
        keys = set(left) | set(right)
        differences = [abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys]
        local_maximum = max(differences, default=0.0)
        surface_maxima[surface] = local_maximum
        maximum = max(maximum, local_maximum)
        difference_count += sum(value > tolerance for value in differences)
        compared += len(keys)
    objective_difference = abs(separate_objective - vectorized_objective)
    return {
        "passed": objective_difference <= tolerance and difference_count == 0,
        "tolerance": tolerance,
        "objective_absolute_difference": objective_difference,
        "maximum_variable_absolute_difference": maximum,
        "above_tolerance_variable_count": difference_count,
        "compared_variable_count": compared,
        "surface_maximum_absolute_differences": surface_maxima,
    }


def _solve(
    case: ReserveCase,
) -> tuple[BuiltModel, HvdcSolveOutcome, dict[str, float], dict[str, Any]]:
    started = time.perf_counter()
    built = ModelAssembler().assemble(reserve_formulation(), case)
    built_at = time.perf_counter()
    policy_type = cast(type[HvdcSolvePolicy], built.formulation.solve_policy)
    outcome = policy_type().solve(built)
    finished = time.perf_counter()
    primary = outcome.primary_mip
    economics = {
        name: float(
            pyo.value(outcome.pricing_model.artifacts[name], exception=False) or 0.0
        )
        for name in (
            "system_cost",
            "system_benefit",
            "system_penalty",
            "scarcity_cost",
            "movement_cost",
            "balance_penalty",
            "ramp_penalty",
        )
    }
    return (
        built,
        outcome,
        {
            "build_seconds": built_at - started,
            "solve_seconds": finished - built_at,
            "total_seconds": finished - started,
        },
        {
            "case_id": case.case_id,
            "period_count": len(case.periods),
            "primary_objective": outcome.primary_snapshot.objective,
            "pricing_objective": outcome.pricing_snapshot.objective,
            "fixed_discrete_count": len(outcome.fixed_discrete),
            "fixed_sos_member_count": len(outcome.fixed_sos_members),
            "primary_best_bound": primary.best_bound if primary is not None else None,
            "primary_relative_gap": primary.relative_gap
            if primary is not None
            else None,
            "primary_solver_version": (
                list(primary.solve.version) if primary is not None else None
            ),
            "pricing_solver_version": list(outcome.pricing_lp.version),
            "detected_issue_count": len(outcome.detected_issues),
            "cross_period_constraints": _cross_period_constraints(
                outcome.primary_model
            ),
            "support_polishing": (
                None
                if outcome.sos_support_polishing is None
                else {
                    "attempted": outcome.sos_support_polishing.attempted,
                    "accepted": outcome.sos_support_polishing.accepted,
                    "reason": outcome.sos_support_polishing.reason,
                    "objective_improvement": (
                        outcome.sos_support_polishing.objective_improvement
                    ),
                }
            ),
            "economics": economics,
        },
    )


def _measure(
    cases: Sequence[ReserveCase],
    *,
    vectorized: bool,
    vectorized_sos: SosRepresentation,
) -> dict[str, Any]:
    gc.collect()
    started = time.perf_counter()
    objectives: list[float] = []
    values: dict[str, dict[tuple[str, ...], float]] = {
        name: {} for name in _PARITY_SURFACES
    }
    timings: list[dict[str, float]] = []
    sizes: list[dict[str, int]] = []
    solve_details: list[dict[str, Any]] = []
    solve_cases: tuple[ReserveCase, ...]
    if vectorized:
        merged = merge_reserve_cases(cases)
        assert merged.hvdc is not None
        merged = replace(
            merged,
            hvdc=replace(merged.hvdc, sos_representation=vectorized_sos),
        )
        solve_cases = (merged,)
    else:
        solve_cases = tuple(cases)
    for case in solve_cases:
        built, outcome, timing, detail = _solve(case)
        timings.append(timing)
        sizes.append(_model_size(built))
        solve_details.append(detail)
        objectives.append(outcome.pricing_snapshot.objective)
        for surface, entries in _solution_values(outcome).items():
            overlap = set(values[surface]).intersection(entries)
            if overlap:
                raise CaseMergeError(f"duplicate solution identities for {surface}")
            values[surface].update(entries)
    elapsed = time.perf_counter() - started
    return {
        "mode": "vectorized" if vectorized else "separate",
        "model_count": len(solve_cases),
        "wall_seconds": elapsed,
        "build_seconds": sum(item["build_seconds"] for item in timings),
        "solve_seconds": sum(item["solve_seconds"] for item in timings),
        "model_sizes": sizes,
        "solve_details": solve_details,
        "aggregate_model_size": {
            name: sum(item[name] for item in sizes) for name in sizes[0]
        },
        "pricing_objective": sum(objectives),
        "values": values,
    }


def _jsonable_measurement(measurement: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in measurement.items() if key != "values"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--periods", type=int, default=4)
    parser.add_argument("--start-ordinal", type=int, default=0)
    parser.add_argument(
        "--execution-order",
        choices=("vectorized-first", "separate-first"),
        default="vectorized-first",
    )
    parser.add_argument(
        "--vectorized-sos",
        choices=("native", "portable"),
        default="native",
        help="SOS2 representation for the combined model; separate solves retain native SOS2",
    )
    args = parser.parse_args()
    if args.periods < 2:
        parser.error("--periods must be at least 2")

    source = args.input.resolve()
    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=source,
        output_directory=args.output.resolve().parent / "unused-report-output",
        source_sha256=_file_sha256(source),
        gams_system_directory=args.system_directory,
    )
    prepare_started = time.perf_counter()
    prepared = _take_distinct_trading_periods(
        PyspdApplication().iter_prepared_cases(
            configuration,
            start_ordinal=args.start_ordinal,
        ),
        args.periods,
    )
    if len(prepared) != args.periods:
        raise CaseMergeError(
            f"requested {args.periods} periods but selected {len(prepared)}"
        )
    cases = tuple(_updated_case(item) for item in prepared)
    preparation_seconds = time.perf_counter() - prepare_started

    order = (
        (True, False) if args.execution_order == "vectorized-first" else (False, True)
    )
    vectorized_sos = (
        SosRepresentation.NATIVE
        if args.vectorized_sos == "native"
        else SosRepresentation.PORTABLE
    )
    measurements = {
        item["mode"]: item
        for flag in order
        for item in (
            _measure(
                cases,
                vectorized=flag,
                vectorized_sos=vectorized_sos,
            ),
        )
    }
    separate = measurements["separate"]
    vectorized = measurements["vectorized"]
    parity = _parity_summary(
        separate_objective=separate["pricing_objective"],
        vectorized_objective=vectorized["pricing_objective"],
        separate_values=separate["values"],
        vectorized_values=vectorized["values"],
        tolerance=1e-6,
    )
    speedup = separate["wall_seconds"] / vectorized["wall_seconds"]
    payload = {
        "schema_version": 1,
        "scope": "initial-solve-only-no-shortfall-transfer-loop",
        "source": {
            "path": str(args.input),
            "sha256": configuration.source_sha256,
        },
        "selection": {
            "policy": "first-case-from-each-distinct-trading-period",
            "start_ordinal": args.start_ordinal,
            "period_count": len(cases),
            "case_ids": [item.specification.case_id for item in prepared],
            "trading_periods": [item.specification.trading_period for item in prepared],
        },
        "preparation_seconds": preparation_seconds,
        "execution_order": args.execution_order,
        "solver_path": "SCIP MIP -> fixed HiGHS RMIP",
        "vectorized_sos_representation": vectorized_sos.value,
        "separate": _jsonable_measurement(separate),
        "vectorized": _jsonable_measurement(vectorized),
        "comparison": {
            "separate_over_vectorized_wall_speedup": speedup,
            "wall_seconds_saved": separate["wall_seconds"] - vectorized["wall_seconds"],
            "vectorized_wall_percent_change": (
                (vectorized["wall_seconds"] / separate["wall_seconds"] - 1.0) * 100.0
            ),
            "parity": parity,
        },
        "limitations": [
            "Memory is inferred from model size; this timing run does not instrument allocations.",
            "The benchmark does not execute period-local shortfall transfer re-solves.",
            "A vectorized model removes process-level dynamic scheduling and period warm starts.",
            "Independent periods share one objective but have no inter-period constraints.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
