"""Run the pinned full-formulation case through Gate 8 and emit JSON evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import statistics
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pyspd.data.gdx import GdxAdapter
from pyspd.orchestration import (
    DailyCasePreparer,
    DailyCaseSelector,
    DailyRunConfiguration,
    DailyRunner,
    IndependentPublicationValidator,
    OverrideApplier,
    ReserveCaseExecutor,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gdx", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--oracle-output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    symbols = GdxAdapter.read(args.gdx, system_directory=args.system_directory)
    selector = DailyCaseSelector()
    selected = selector.select(symbols)
    if len(selected) != 1:
        raise ValueError(f"expected one selected case, found {len(selected)}")
    case_data = selector.case_data(symbols, selected[0])
    case_data, override_audit = OverrideApplier().apply(case_data, ())
    prepared = DailyCasePreparer().prepare(
        case_data,
        selected[0],
        daily_mode=True,
        override_audit=override_audit,
    )
    configuration = DailyRunConfiguration(
        "vspd-v5.0.6-reserve",
        symbols.source_sha256,
        maximum_solve_loops=prepared.maximum_solve_loops or 5,
        daily_mode=True,
        environment_fingerprint=(
            f"{platform.system()}-{platform.machine()}-gams54-scip-highs"
        ),
    )
    result = DailyRunner(ReserveCaseExecutor()).run(configuration, (prepared,))
    assert result.published is not None
    independent = IndependentPublicationValidator().validate(
        result.cases, result.published
    )
    expected_energy = _energy_oracle(
        args.oracle_output / "gate1_semantic_v2_PublishedEnergyPrices_TP.csv"
    )
    expected_reserve = _reserve_oracle(
        args.oracle_output / "gate1_semantic_v2_PublishedReservePrices_TP.csv"
    )
    energy_errors = {
        key: abs(result.published.energy[key] - value)
        for key, value in expected_energy.items()
        if key in result.published.energy
    }
    reserve_errors = {
        key: abs(result.published.reserve[key] - value)
        for key, value in expected_reserve.items()
        if key in result.published.reserve
    }
    accepted = result.cases[0].accepted
    assert accepted is not None
    solve_payload = accepted.solve_payload
    fixed_discrete = dict(solve_payload.fixed_discrete)
    identity_passed = set(expected_energy) == set(result.published.energy) and set(
        expected_reserve
    ) == set(result.published.reserve)
    tolerance = 1e-4
    evidence = {
        "schema_version": 1,
        "profile": "macos-arm64-gams54-scip-highs",
        "source": {
            "name": args.gdx.name,
            "sha256": symbols.source_sha256,
        },
        "case": {
            "case_id": selected[0].case_id,
            "date_time": selected[0].date_time,
            "trading_period": selected[0].trading_period,
            "schedule_type": selected[0].schedule_type.value,
            "publication_seconds": selected[0].publication_seconds,
        },
        "state_machine": {
            "state": result.state.value,
            "case_status": result.cases[0].status.value,
            "solve_count": result.cases[0].solve_count,
            "event_kinds": [event.kind.value for event in result.events],
            "transfer_count": len(result.cases[0].transfers),
            "untransferred_count": len(result.cases[0].untransferred_nodes),
            "primary_objective_nzd": accepted.objective,
            "pricing_objective_nzd": solve_payload.pricing_snapshot.objective,
            "primary_backend": solve_payload.primary_mip.solve.backend,
            "pricing_backend": solve_payload.pricing_lp.backend,
            "fixed_discrete_count": len(fixed_discrete),
            "fixed_discrete_sha256": hashlib.sha256(
                json.dumps(
                    fixed_discrete, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            "detected_issues": list(solve_payload.detected_issues),
        },
        "published_oracle_comparison": {
            "identity_sets_equal": identity_passed,
            "energy_price_count": len(energy_errors),
            "reserve_price_count": len(reserve_errors),
            "maximum_energy_absolute_error": max(energy_errors.values(), default=0.0),
            "maximum_reserve_absolute_error": max(reserve_errors.values(), default=0.0),
            "energy_error_summary": _error_summary(energy_errors),
            "reserve_error_summary": _error_summary(reserve_errors),
            "tolerance": tolerance,
        },
        "independent_validation": {
            "passed": independent.passed,
            "check_count": independent.check_count,
            "maximum_absolute_error": independent.maximum_absolute_error,
            "failures": list(independent.failures),
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    comparison = evidence["published_oracle_comparison"]
    assert isinstance(comparison, dict)
    evidence["passed"] = bool(
        result.state.value == "complete"
        and identity_passed
        and comparison["maximum_energy_absolute_error"] <= tolerance
        and comparison["maximum_reserve_absolute_error"] <= tolerance
        and independent.passed
    )
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))


def _energy_oracle(path: Path) -> dict[tuple[str, str], float]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["TradingPeriod"], row["Pnodename"]): float(
                row["vSPDDollarsPerMegawattHour"]
            )
            for row in csv.DictReader(handle)
        }


def _reserve_oracle(path: Path) -> dict[tuple[str, str, str], float]:
    output: dict[tuple[str, str, str], float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            period = row["TradingPeriod"]
            island = row["Island"]
            output[(period, island, "FIR")] = float(
                row["vSPDFIRDollarsPerMegawattHour"]
            )
            output[(period, island, "SIR")] = float(
                row["vSPDSIRDollarsPerMegawattHour"]
            )
    return output


def _error_summary(errors: Mapping[Any, float]) -> dict[str, object]:
    ordered = sorted(errors.values())
    top = sorted(errors.items(), key=lambda item: item[1], reverse=True)[:10]
    return {
        "mean_absolute_error": statistics.fmean(ordered) if ordered else 0.0,
        "median_absolute_error": statistics.median(ordered) if ordered else 0.0,
        "above_tolerance_count": sum(value > 1e-4 for value in ordered),
        "top_absolute_errors": [
            {"identity": list(key), "absolute_error": value} for key, value in top
        ],
    }


if __name__ == "__main__":
    main()
