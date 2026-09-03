"""Stream a full-day benchmark of MIP-to-fixed-RMIP solver paths."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import platform
import time
from collections.abc import Callable, Mapping
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import Any, TextIO

from pyspd.application import (
    CBC_CLP_VALIDATION_SOLVER_PROFILE,
    CBC_HIGHS_VALIDATION_SOLVER_PROFILE,
    CLP_VALIDATION_SOLVER_PROFILE,
    PORTABLE_SOLVER_PROFILE,
    ApplicationConfiguration,
    PyspdApplication,
)
from pyspd.data import SUPPORTED_INPUT_SCHEMAS, V5_INPUT_SCHEMA
from pyspd.orchestration import (
    DailyCaseRunner,
    DailyRunResult,
    DailyRunState,
    OrchestrationError,
)
from pyspd.orchestration.pricing import PublishedPriceAccumulator
from pyspd.orchestration.types import PreparedCase, SolveObservation
from pyspd.reserve import RESERVE_FORMULATION_ID, IndependentReserveValidator

PROFILES = (
    PORTABLE_SOLVER_PROFILE,
    CLP_VALIDATION_SOLVER_PROFILE,
    CBC_HIGHS_VALIDATION_SOLVER_PROFILE,
    CBC_CLP_VALIDATION_SOLVER_PROFILE,
)
PHYSICS_SURFACES = ("generation", "energy_shortfall", "bus_generation", "bus_load")
PRICE_SURFACES = ("raw_bus", "repaired_bus", "node", "reserve")
REPORT_TABLES = (
    "summary",
    "island",
    "bus",
    "node",
    "offer",
    "bid",
    "reserve",
    "risk",
    "branch",
    "constraint",
)


class ProgressExecutor:
    """Time solve calls while preserving the underlying executor contract."""

    def __init__(self, profile: str, delegate: Any) -> None:
        self.profile = profile
        self.delegate = delegate
        self.solve_calls = 0
        self.solve_seconds = 0.0

    def solve(self, prepared: PreparedCase) -> SolveObservation:
        started = time.perf_counter()
        try:
            return self.delegate.solve(prepared)
        finally:
            self.solve_seconds += time.perf_counter() - started
            self.solve_calls += 1


def _execute_with_retries(
    execute: Callable[[], Any],
    *,
    maximum_attempts: int,
    on_retry: Callable[[int, OrchestrationError], None],
) -> Any:
    """Retry an isolated case only after an orchestration/solver failure."""

    for attempt in range(1, maximum_attempts + 1):
        try:
            return execute()
        except OrchestrationError as error:
            if attempt == maximum_attempts:
                raise
            on_retry(attempt, error)
    raise AssertionError("unreachable retry state")


def _record_retry(
    case_retries: list[dict[str, Any]],
    case_id: str,
    attempt: int,
    error: OrchestrationError,
) -> None:
    event = {
        "case_id": case_id,
        "failed_attempt": attempt,
        "error": str(error),
    }
    case_retries.append(event)
    print(json.dumps({"retry": event}, sort_keys=True), flush=True)
    gc.collect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int)
    parser.add_argument("--case-ids", nargs="+", default=[])
    parser.add_argument("--start-ordinal", type=int, default=0)
    parser.add_argument("--maximum-cases", type=int)
    parser.add_argument("--maximum-case-attempts", type=int, default=2)
    parser.add_argument("--validation-tolerance", type=float, default=1e-4)
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=PROFILES,
        default=list(PROFILES),
    )
    parser.add_argument(
        "--input-schema",
        choices=sorted(SUPPORTED_INPUT_SCHEMAS),
        default=V5_INPUT_SCHEMA,
    )
    args = parser.parse_args()
    if args.start_ordinal < 0:
        parser.error("--start-ordinal must be non-negative")
    if args.maximum_cases is not None and args.maximum_cases <= 0:
        parser.error("--maximum-cases must be positive")
    if args.maximum_case_attempts <= 0:
        parser.error("--maximum-case-attempts must be positive")

    source_sha256 = _file_sha256(args.input)
    payload: dict[str, Any] = {
        "schema_version": 5,
        "profile": "pyspd-streaming-full-day-selected-solver-path-benchmark-v5",
        "source_name": args.input.name,
        "source_sha256": source_sha256,
        "expected_case_count": args.expected_case_count,
        "input_schema": args.input_schema,
        "selected_profiles": list(args.profiles),
        "environment": f"{platform.system()}-{platform.machine()}",
        "versions": {
            package: version(package)
            for package in ("pyomo", "pyscipopt", "highspy", "cylp", "pulp")
        },
        "validation_tolerance": args.validation_tolerance,
        "runs": [],
    }
    baseline_records = _records_path(args.output, PORTABLE_SOLVER_PROFILE)
    for profile in args.profiles:
        reference_records = (
            baseline_records
            if profile != PORTABLE_SOLVER_PROFILE
            and PORTABLE_SOLVER_PROFILE in args.profiles[: args.profiles.index(profile)]
            else None
        )
        record = _run_profile(
            args,
            source_sha256,
            profile,
            reference_records,
        )
        payload["runs"].append(record)
        _finish_payload(payload)
        _write(args.output, payload)
        print(
            json.dumps(
                {
                    key: record.get(key)
                    for key in (
                        "profile",
                        "completed",
                        "case_count",
                        "wall_seconds",
                        "solve_seconds",
                        "solve_calls",
                        "all_solves_optimal",
                        "independent_validation_passed",
                        "maximum_validation_residual",
                        "records_sha256",
                        "error_type",
                        "error",
                    )
                    if key in record
                },
                sort_keys=True,
            ),
            flush=True,
        )


def _run_profile(
    args: argparse.Namespace,
    source_sha256: str,
    profile: str,
    baseline_path: Path | None,
) -> dict[str, Any]:
    app = PyspdApplication()
    configuration = _configuration(args, source_sha256, profile)
    executor = ProgressExecutor(profile, app.case_executor(configuration))
    runner = DailyCaseRunner(
        executor,
        postprocessor=app.price_postprocessor(configuration),
    )
    daily_configuration = app.daily_configuration(configuration)
    records_path = _records_path(args.output, profile)
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.unlink(missing_ok=True)
    baseline: TextIO | None = (
        baseline_path.open(encoding="utf-8") if baseline_path is not None else None
    )
    previous_generation: dict[str, float] = {}
    event_sequence = 0
    case_count = 0
    all_optimal = True
    all_validated = True
    maximum_validation_residual = 0.0
    parity = _empty_parity(profile)
    parity["comparison_available"] = bool(
        profile == PORTABLE_SOLVER_PROFILE or baseline is not None
    )
    published_accumulator = PublishedPriceAccumulator()
    case_retries: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        with records_path.open("w", encoding="utf-8") as records:
            for prepared in app.iter_prepared_cases(
                configuration, start_ordinal=args.start_ordinal
            ):
                if (
                    args.maximum_cases is not None
                    and case_count >= args.maximum_cases
                ):
                    break
                execution = _execute_with_retries(
                    partial(
                        runner.execute,
                        daily_configuration,
                        prepared,
                        previous_generation=previous_generation,
                        event_sequence=event_sequence,
                    ),
                    maximum_attempts=args.maximum_case_attempts,
                    on_retry=partial(
                        _record_retry,
                        case_retries,
                        prepared.specification.case_id,
                    ),
                )
                result = execution.result
                accepted = result.accepted
                if accepted is None:
                    raise ValueError(
                        f"case {prepared.specification.case_id} has no accepted result"
                    )
                outcome = accepted.solve_payload
                primary = (
                    outcome.primary_mip.solve
                    if outcome.primary_mip is not None
                    else outcome.initial_solve
                )
                case_optimal = (
                    primary.status.value == "optimal"
                    and outcome.pricing_lp.status.value == "optimal"
                )
                validation = IndependentReserveValidator().validate(
                    outcome,
                    tolerance=args.validation_tolerance,
                )
                residual_name, residual = max(
                    validation.residuals.items(),
                    key=lambda item: item[1],
                    default=(None, 0.0),
                )
                case_record = _case_record(
                    result,
                    case_optimal,
                    validation.passed,
                    residual,
                    residual_name,
                    _case_reports(app, configuration, daily_configuration, result),
                )
                published_accumulator.add(result)
                records.write(json.dumps(case_record, sort_keys=True) + "\n")
                records.flush()
                if baseline is not None:
                    reference_line = baseline.readline()
                    if not reference_line:
                        raise ValueError("candidate contains more cases than reference")
                    _update_parity(parity, json.loads(reference_line), case_record)
                case_count += 1
                all_optimal &= case_optimal
                all_validated &= validation.passed
                maximum_validation_residual = max(maximum_validation_residual, residual)
                previous_generation = execution.previous_generation
                event_sequence = execution.next_event_sequence
                if case_count == 1 or case_count % 10 == 0:
                    print(
                        json.dumps(
                            {
                                "profile": profile,
                                "completed_cases": case_count,
                                "solve_calls": executor.solve_calls,
                                "latest_case_id": prepared.specification.case_id,
                                "solve_seconds": executor.solve_seconds,
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                del execution, result, accepted, outcome, validation, case_record
                # PySCIPOpt/SCIP objects participate in reference cycles.  A
                # full report record is deliberately released after every
                # period so SCIP's preceding model and SoPlex instance are
                # finalized before the next MIP is constructed.  Waiting for
                # periodic cyclic GC reproducibly made the third legacy-v3
                # period fail inside SoPlex despite that period solving when
                # run in isolation.
                gc.collect()
        if baseline is not None and baseline.readline():
            raise ValueError("candidate contains fewer cases than reference")
        expected = args.expected_case_count
        count_matches = expected is None or case_count == expected
        _finalize_parity(parity)
        published = published_accumulator.finish(
            decimals=daily_configuration.price_rounding_decimals
        )
        return {
            "profile": profile,
            "completed": count_matches,
            "case_count": case_count,
            "expected_case_count_match": count_matches,
            "wall_seconds": time.perf_counter() - started,
            "solve_seconds": executor.solve_seconds,
            "solve_calls": executor.solve_calls,
            "case_retry_count": len(case_retries),
            "case_retries": case_retries,
            "all_solves_optimal": all_optimal,
            "independent_validation_passed": all_validated,
            "maximum_validation_residual": maximum_validation_residual,
            "records_path": str(records_path),
            "records_sha256": _file_sha256(records_path),
            "published_price_rows": _published_price_rows(published),
            "parity": parity,
        }
    except (OSError, RuntimeError, ValueError) as error:
        _finalize_parity(parity)
        return {
            "profile": profile,
            "completed": False,
            "case_count": case_count,
            "wall_seconds": time.perf_counter() - started,
            "solve_seconds": executor.solve_seconds,
            "solve_calls": executor.solve_calls,
            "case_retry_count": len(case_retries),
            "case_retries": case_retries,
            "error_type": type(error).__name__,
            "error": str(error),
            "records_path": str(records_path),
            "parity": parity,
        }
    finally:
        if baseline is not None:
            baseline.close()


def _case_record(
    result: Any,
    optimal: bool,
    validation_passed: bool,
    maximum_validation_residual: float,
    maximum_validation_residual_name: str | None,
    reports: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    accepted = result.accepted
    prices = result.prices
    assert accepted is not None and prices is not None
    outcome = accepted.solve_payload
    return {
        "case_id": result.specification.case_id,
        "date_time": result.specification.date_time,
        "trading_period": result.specification.trading_period,
        "publication_seconds": result.specification.publication_seconds.hex(),
        "solve_count": result.solve_count,
        "optimal": optimal,
        "validation_passed": validation_passed,
        "maximum_validation_residual": maximum_validation_residual,
        "maximum_validation_residual_name": maximum_validation_residual_name,
        "primary_objective": outcome.primary_snapshot.objective.hex(),
        "pricing_objective": outcome.pricing_snapshot.objective.hex(),
        "fixed_discrete": _mapping(outcome.fixed_discrete),
        "physics": {
            name: _mapping(getattr(accepted, name)) for name in PHYSICS_SURFACES
        },
        "prices": {name: _mapping(getattr(prices, name)) for name in PRICE_SURFACES},
        "reports": reports,
    }


def _case_reports(
    app: PyspdApplication,
    configuration: ApplicationConfiguration,
    daily_configuration: Any,
    result: Any,
) -> dict[str, list[dict[str, str]]]:
    one_case = DailyRunResult(
        DailyRunState.COMPLETE,
        daily_configuration.logical_sha256,
        (result,),
        None,
        result.events,
    )
    bundle = app.render_report_bundle(configuration, one_case)
    reports = {
        name: [dict(row) for row in bundle.tables[name].rows] for name in REPORT_TABLES
    }
    reports["constraint"] = [
        row
        for row in reports["constraint"]
        if row["constraint"].startswith(
            (
                "NetworkSecurity.BranchSecurityConstraint",
                "NetworkSecurity.MNodeSecurityConstraint",
            )
        )
    ]
    return reports


def _mapping(values: Mapping[Any, float]) -> list[list[Any]]:
    records = []
    for raw_key, raw_value in values.items():
        key = raw_key if isinstance(raw_key, tuple) else (raw_key,)
        records.append([list(map(str, key)), float(raw_value).hex()])
    return sorted(records, key=lambda item: item[0])


def _published_price_rows(published: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    energy_intervals = getattr(published, "energy_intervals", {})
    for (period, node), price in sorted(published.energy.items()):
        interval = energy_intervals.get((period, node))
        rows.append(
            {
                "trading_period": period,
                "location": node,
                "product": "energy",
                "price_nzd_per_mwh": format(float(price), ".17g"),
                "price_interval": (
                    ""
                    if interval is None
                    else "["
                    + ",".join(format(float(bound), ".17g") for bound in interval)
                    + "]"
                ),
                "publication_seconds": format(
                    float(published.total_seconds[period]), ".17g"
                ),
                "date_time": published.date_time[period],
            }
        )
    for (period, island, reserve_class), price in sorted(
        published.reserve.items()
    ):
        rows.append(
            {
                "trading_period": period,
                "location": island,
                "product": reserve_class,
                "price_nzd_per_mwh": format(float(price), ".17g"),
                "price_interval": "",
                "publication_seconds": format(
                    float(published.total_seconds[period]), ".17g"
                ),
                "date_time": published.date_time[period],
            }
        )
    return rows


def _empty_parity(profile: str) -> dict[str, Any]:
    return {
        "reference_profile": PORTABLE_SOLVER_PROFILE,
        "self_reference": profile == PORTABLE_SOLVER_PROFILE,
        "identity_match": True,
        "fixed_discrete_match": True,
        "solve_count_match": True,
        "maximum_primary_objective_error": 0.0,
        "maximum_pricing_objective_error": 0.0,
        "maximum_physics_error": 0.0,
        "maximum_raw_bus_price_error": 0.0,
        "maximum_market_price_error": 0.0,
        "compared_value_count": 0,
    }


def _update_parity(
    parity: dict[str, Any],
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> None:
    parity["identity_match"] &= (
        reference["case_id"] == candidate["case_id"]
        and reference["date_time"] == candidate["date_time"]
    )
    parity["solve_count_match"] &= reference["solve_count"] == candidate["solve_count"]
    parity["fixed_discrete_match"] &= (
        reference["fixed_discrete"] == candidate["fixed_discrete"]
    )
    parity["maximum_primary_objective_error"] = max(
        parity["maximum_primary_objective_error"],
        abs(
            float.fromhex(reference["primary_objective"])
            - float.fromhex(candidate["primary_objective"])
        ),
    )
    parity["maximum_pricing_objective_error"] = max(
        parity["maximum_pricing_objective_error"],
        abs(
            float.fromhex(reference["pricing_objective"])
            - float.fromhex(candidate["pricing_objective"])
        ),
    )
    for name in PHYSICS_SURFACES:
        error, count, matched = _mapping_error(
            reference["physics"][name], candidate["physics"][name]
        )
        parity["identity_match"] &= matched
        parity["maximum_physics_error"] = max(parity["maximum_physics_error"], error)
        parity["compared_value_count"] += count
    for name in PRICE_SURFACES:
        error, count, matched = _mapping_error(
            reference["prices"][name], candidate["prices"][name]
        )
        parity["identity_match"] &= matched
        target = (
            "maximum_raw_bus_price_error"
            if name == "raw_bus"
            else "maximum_market_price_error"
        )
        parity[target] = max(parity[target], error)
        parity["compared_value_count"] += count


def _mapping_error(
    reference: list[list[Any]], candidate: list[list[Any]]
) -> tuple[float, int, bool]:
    if len(reference) != len(candidate):
        return math.inf, 0, False
    maximum = 0.0
    for left, right in zip(reference, candidate, strict=True):
        if left[0] != right[0]:
            return math.inf, 0, False
        maximum = max(
            maximum,
            abs(float.fromhex(left[1]) - float.fromhex(right[1])),
        )
    return maximum, len(reference), True


def _finalize_parity(parity: dict[str, Any]) -> None:
    if not parity.get("comparison_available", True):
        parity["market_result_parity_passed"] = False
        parity["strict_raw_parity_passed"] = False
        return
    parity["market_result_parity_passed"] = bool(
        parity["identity_match"]
        and parity["fixed_discrete_match"]
        and parity["solve_count_match"]
        and parity["maximum_pricing_objective_error"] <= 1e-4
        and parity["maximum_physics_error"] <= 1e-8
        and parity["maximum_market_price_error"] <= 1e-4
    )
    parity["strict_raw_parity_passed"] = bool(
        parity["market_result_parity_passed"]
        and parity["maximum_primary_objective_error"] <= 1e-4
        and parity["maximum_raw_bus_price_error"] <= 1e-4
    )


def _configuration(
    args: argparse.Namespace,
    source_sha256: str,
    profile: str,
) -> ApplicationConfiguration:
    return ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=args.input,
        output_directory=args.output.parent / f"unused-{profile}",
        source_sha256=source_sha256,
        gams_system_directory=args.system_directory,
        solver_profile=profile,
        input_schema=args.input_schema,
        case_ids=tuple(args.case_ids),
    )


def _finish_payload(payload: dict[str, Any]) -> None:
    completed_optimal = [
        run
        for run in payload["runs"]
        if run.get("completed") and run.get("all_solves_optimal")
    ]
    eligible = [
        run
        for run in payload["runs"]
        if run.get("completed")
        and run.get("all_solves_optimal")
        and run.get("independent_validation_passed")
        and run["parity"].get("market_result_parity_passed")
    ]
    strict = [run for run in eligible if run["parity"].get("strict_raw_parity_passed")]
    payload["fastest_completed_optimal_profile"] = (
        min(completed_optimal, key=lambda run: run["solve_seconds"])["profile"]
        if completed_optimal
        else None
    )
    payload["fastest_optimal_validated_profile"] = (
        min(eligible, key=lambda run: run["solve_seconds"])["profile"]
        if eligible
        else None
    )
    payload["fastest_strict_raw_parity_profile"] = (
        min(strict, key=lambda run: run["solve_seconds"])["profile"] if strict else None
    )


def _records_path(output: Path, profile: str) -> Path:
    return output.with_name(f"{output.stem}-{profile}.jsonl")


def _write(path: Path, payload: dict[str, Any]) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "logical_sha256"}
    payload["logical_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
