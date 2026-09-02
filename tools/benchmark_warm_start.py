"""Benchmark cold and period-to-period warm-started PySPD solves."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from collections.abc import Mapping
from itertools import islice
from pathlib import Path
from typing import Any

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.orchestration import DailyRunner, ReserveCaseExecutor
from pyspd.orchestration.types import DailyRunResult, PreparedCase, SolveObservation
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from tools.gate12.execution_provenance import python_execution_sha256


class TimedExecutor:
    """Measure a class-based executor without changing its solve contract."""

    def __init__(self, *, mode: str) -> None:
        self.delegate = ReserveCaseExecutor(
            warm_start_primary=mode in {"scip", "both"},
            warm_start_pricing=mode in {"highs", "both"},
        )
        self.seconds: list[float] = []
        self.primary_warm_counts: list[int] = []
        self.pricing_warm_counts: list[int] = []

    def solve(self, prepared: PreparedCase) -> SolveObservation:
        started = time.perf_counter()
        result = self.delegate.solve(prepared)
        self.seconds.append(time.perf_counter() - started)
        audit = result.solve_payload.warm_start
        self.primary_warm_counts.append(audit.primary_discrete_count)
        self.pricing_warm_counts.append(audit.pricing_value_count)
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--case-count", type=int, default=12)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("cold", "scip", "highs", "both"),
        default=("cold", "scip", "highs", "both"),
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.case_count < 2 or args.repetitions < 1:
        raise ValueError("case-count must be at least two and repetitions positive")

    source_sha256 = _file_sha256(args.input)
    application = PyspdApplication()
    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=args.input,
        output_directory=args.output.parent / "unused-report-output",
        source_sha256=source_sha256,
        gams_system_directory=args.system_directory,
    )
    prepared_started = time.perf_counter()
    cases = tuple(
        islice(application.iter_prepared_cases(configuration), args.case_count)
    )
    preparation_seconds = time.perf_counter() - prepared_started
    if len(cases) != args.case_count:
        raise ValueError(f"requested {args.case_count} cases, found {len(cases)}")

    modes = tuple(dict.fromkeys(args.modes))
    if "cold" not in modes:
        raise ValueError("benchmark modes must include cold")
    runs: list[dict[str, Any]] = []
    results: dict[str, list[DailyRunResult]] = {mode: [] for mode in modes}
    for repetition in range(args.repetitions):
        order = modes if repetition % 2 == 0 else tuple(reversed(modes))
        for mode in order:
            executor = TimedExecutor(mode=mode)
            started = time.perf_counter()
            result = DailyRunner(executor).run(
                application.daily_configuration(configuration), cases
            )
            wall_seconds = time.perf_counter() - started
            results[mode].append(result)
            runs.append(
                {
                    "repetition": repetition + 1,
                    "mode": mode,
                    "wall_seconds": wall_seconds,
                    "case_solve_seconds": executor.seconds,
                    "primary_warm_start_counts": executor.primary_warm_counts,
                    "pricing_warm_start_counts": executor.pricing_warm_counts,
                    "result_sha256": _result_sha256(result),
                    "all_solves_optimal": _all_solves_optimal(result),
                }
            )

    cold_seconds = [run["wall_seconds"] for run in runs if run["mode"] == "cold"]
    cold_median = statistics.median(cold_seconds)
    summaries = {}
    parity = {}
    for mode in modes:
        seconds = [run["wall_seconds"] for run in runs if run["mode"] == mode]
        median = statistics.median(seconds)
        summaries[mode] = {
            "median_seconds": median,
            "speedup_factor_vs_cold": cold_median / median,
            "elapsed_reduction_percent_vs_cold": 100.0
            * (cold_median - median)
            / cold_median,
        }
        if mode != "cold":
            parity[mode] = _compare(results["cold"][0], results[mode][0])
    unsigned = {
        "schema_version": 1,
        "profile": "pyspd-period-warm-start-benchmark-v1",
        "source_name": args.input.name,
        "source_sha256": source_sha256,
        "execution_sha256": python_execution_sha256(),
        "environment": f"{platform.system()}-{platform.machine()}",
        "case_ids": [case.specification.case_id for case in cases],
        "case_count": len(cases),
        "repetitions": args.repetitions,
        "preparation_seconds": preparation_seconds,
        "runs": runs,
        "summary": summaries,
        "parity": parity,
    }
    payload = {**unsigned, "logical_sha256": _logical_sha256(unsigned)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary": summaries,
                "parity_passed": {
                    mode: result["passed"] for mode, result in parity.items()
                },
                "logical_sha256": payload["logical_sha256"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _compare(reference: DailyRunResult, candidate: DailyRunResult) -> dict[str, Any]:
    identity_match = [case.specification.case_id for case in reference.cases] == [
        case.specification.case_id for case in candidate.cases
    ]
    maximum_objective = 0.0
    maximum_physics = 0.0
    maximum_price = 0.0
    fixed_discrete_match = True
    compared_values = 0
    if identity_match:
        for cold_case, warm_case in zip(reference.cases, candidate.cases, strict=True):
            cold = cold_case.accepted
            warm = warm_case.accepted
            assert cold is not None and warm is not None
            maximum_objective = max(
                maximum_objective,
                abs(cold.objective - warm.objective),
                abs(
                    cold.solve_payload.primary_snapshot.objective
                    - warm.solve_payload.primary_snapshot.objective
                ),
            )
            for name in (
                "generation",
                "energy_shortfall",
                "bus_generation",
                "bus_load",
            ):
                error, count, matched = _mapping_error(
                    getattr(cold, name), getattr(warm, name)
                )
                identity_match &= matched
                maximum_physics = max(maximum_physics, error)
                compared_values += count
            assert cold_case.prices is not None and warm_case.prices is not None
            for name in ("raw_bus", "repaired_bus", "node", "reserve"):
                error, count, matched = _mapping_error(
                    getattr(cold_case.prices, name), getattr(warm_case.prices, name)
                )
                identity_match &= matched
                maximum_price = max(maximum_price, error)
                compared_values += count
            fixed_discrete_match &= (
                dict(cold.solve_payload.fixed_discrete)
                == dict(warm.solve_payload.fixed_discrete)
            )
    published_match = _published_payload(reference) == _published_payload(candidate)
    passed = (
        identity_match
        and fixed_discrete_match
        and published_match
        and maximum_objective <= 1e-4
        and maximum_physics <= 1e-8
        and maximum_price <= 1e-4
        and _all_solves_optimal(reference)
        and _all_solves_optimal(candidate)
    )
    return {
        "passed": passed,
        "identity_match": identity_match,
        "fixed_discrete_match": fixed_discrete_match,
        "published_output_exact_match": published_match,
        "exact_result_sha256_match": _result_sha256(reference)
        == _result_sha256(candidate),
        "compared_value_count": compared_values,
        "maximum_objective_error": maximum_objective,
        "maximum_physics_error": maximum_physics,
        "maximum_price_error": maximum_price,
        "objective_tolerance": 1e-4,
        "physics_tolerance": 1e-8,
        "price_tolerance": 1e-4,
    }


def _mapping_error(
    reference: Mapping[Any, float], candidate: Mapping[Any, float]
) -> tuple[float, int, bool]:
    if set(reference) != set(candidate):
        return float("inf"), 0, False
    errors = [abs(float(reference[key]) - float(candidate[key])) for key in reference]
    return max(errors, default=0.0), len(errors), True


def _all_solves_optimal(result: DailyRunResult) -> bool:
    for case in result.cases:
        if case.accepted is None:
            return False
        outcome = case.accepted.solve_payload
        primary = outcome.primary_mip.solve if outcome.primary_mip else outcome.initial_solve
        if primary.status.value != "optimal" or outcome.pricing_lp.status.value != "optimal":
            return False
    return True


def _result_sha256(result: DailyRunResult) -> str:
    payload = {
        "cases": [
            {
                "case_id": case.specification.case_id,
                "status": case.status.value,
                "solve_count": case.solve_count,
                "accepted": _observation_payload(case.accepted),
                "prices": None
                if case.prices is None
                else {
                    name: _mapping_payload(getattr(case.prices, name))
                    for name in ("raw_bus", "repaired_bus", "node", "reserve")
                },
            }
            for case in result.cases
        ],
        "published": _published_payload(result),
    }
    return _logical_sha256(payload)


def _observation_payload(observation: SolveObservation | None) -> Any:
    if observation is None:
        return None
    outcome = observation.solve_payload
    return {
        "objective": observation.objective.hex(),
        "mappings": {
            name: _mapping_payload(getattr(observation, name))
            for name in (
                "generation",
                "energy_shortfall",
                "bus_generation",
                "bus_load",
                "raw_bus_prices",
                "reserve_prices",
            )
        },
        "primary_objective": outcome.primary_snapshot.objective.hex(),
        "pricing_objective": outcome.pricing_snapshot.objective.hex(),
        "fixed_discrete": dict(sorted(outcome.fixed_discrete.items())),
        "fixed_sos_members": dict(sorted(outcome.fixed_sos_members.items())),
    }


def _published_payload(result: DailyRunResult) -> Any:
    if result.published is None:
        return None
    return {
        "energy": _mapping_payload(result.published.energy),
        "reserve": _mapping_payload(result.published.reserve),
        "total_seconds": _mapping_payload(result.published.total_seconds),
    }


def _mapping_payload(values: Mapping[Any, float]) -> list[dict[str, Any]]:
    rows = []
    for key, value in values.items():
        identity = key if isinstance(key, tuple) else (key,)
        rows.append(
            {
                "identity": [str(token) for token in identity],
                "value": float(value).hex(),
            }
        )
    return sorted(rows, key=lambda row: row["identity"])


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


if __name__ == "__main__":
    main()
