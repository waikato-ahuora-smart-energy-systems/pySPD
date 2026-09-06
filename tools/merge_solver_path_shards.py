"""Merge ordered benchmark shards without weakening their evidence checks."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TextIO

from tools.benchmark_solver_paths import (
    _empty_parity,
    _file_sha256,
    _finalize_parity,
    _finish_payload,
    _published_price_rows,
    _records_path,
    _update_parity,
    _write,
)
from tools.evidence_paths import repository_evidence_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference-records", type=Path)
    args = parser.parse_args()

    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.shard]
    runs = [payload["runs"][0] for payload in payloads]
    _validate(payloads, runs)
    profile = runs[0]["profile"]
    records_path = _records_path(args.output, profile)
    records_path.parent.mkdir(parents=True, exist_ok=True)

    energy_numerator: dict[tuple[str, str], float] = defaultdict(float)
    energy_lower_numerator: dict[tuple[str, str], float] = defaultdict(float)
    energy_upper_numerator: dict[tuple[str, str], float] = defaultdict(float)
    energy_interval_keys: set[tuple[str, str]] = set()
    reserve_numerator: dict[tuple[str, str, str], float] = defaultdict(float)
    reserve_lower_numerator: dict[tuple[str, str, str], float] = defaultdict(float)
    reserve_upper_numerator: dict[tuple[str, str, str], float] = defaultdict(float)
    reserve_interval_keys: set[tuple[str, str, str]] = set()
    total_seconds: dict[str, float] = defaultdict(float)
    date_time: dict[str, str] = {}
    seen: set[tuple[str, str, str]] = set()
    case_count = 0
    reference: TextIO | None = (
        args.reference_records.open(encoding="utf-8")
        if args.reference_records is not None
        else None
    )
    parity = _empty_parity(profile)
    parity["comparison_available"] = bool(
        profile == parity["reference_profile"] or reference is not None
    )
    try:
        with records_path.open("w", encoding="utf-8") as target:
            for run in runs:
                with repository_evidence_path(Path.cwd(), run["records_path"]).open(encoding="utf-8") as source:
                    for line in source:
                        record = json.loads(line)
                        identity = _record_identity(record)
                        if identity in seen:
                            raise ValueError(f"duplicate shard case: {identity!r}")
                        seen.add(identity)
                        target.write(line)
                        _accumulate_published(
                            record,
                            energy_numerator,
                            reserve_numerator,
                            total_seconds,
                            date_time,
                            energy_lower_numerator=energy_lower_numerator,
                            energy_upper_numerator=energy_upper_numerator,
                            energy_interval_keys=energy_interval_keys,
                            reserve_lower_numerator=reserve_lower_numerator,
                            reserve_upper_numerator=reserve_upper_numerator,
                            reserve_interval_keys=reserve_interval_keys,
                        )
                        if reference is not None:
                            reference_line = reference.readline()
                            if not reference_line:
                                raise ValueError(
                                    "candidate shards contain more cases than reference"
                                )
                            _update_parity(
                                parity, json.loads(reference_line), record
                            )
                        case_count += 1
        if reference is not None and reference.readline():
            raise ValueError("candidate shards contain fewer cases than reference")
    finally:
        if reference is not None:
            reference.close()

    published = SimpleNamespace(
        energy={
            key: round(value / total_seconds[key[0]], 5)
            for key, value in energy_numerator.items()
        },
        reserve={
            key: round(value / total_seconds[key[0]], 5)
            for key, value in reserve_numerator.items()
        },
        energy_intervals={
            key: (
                round(energy_lower_numerator[key] / total_seconds[key[0]], 5),
                round(energy_upper_numerator[key] / total_seconds[key[0]], 5),
            )
            for key in energy_interval_keys
        },
        reserve_intervals={
            key: (
                round(reserve_lower_numerator[key] / total_seconds[key[0]], 5),
                round(reserve_upper_numerator[key] / total_seconds[key[0]], 5),
            )
            for key in reserve_interval_keys
        },
        total_seconds=total_seconds,
        date_time=date_time,
    )
    _finalize_parity(parity)
    first = payloads[0]
    expected = sum(int(run["case_count"]) for run in runs)
    run = {
        "profile": profile,
        "completed": all(bool(run.get("completed")) for run in runs),
        "case_count": case_count,
        "expected_case_count_match": case_count == expected,
        "wall_seconds": max(float(run["wall_seconds"]) for run in runs),
        "solve_seconds": sum(float(run["solve_seconds"]) for run in runs),
        "solve_calls": sum(int(run["solve_calls"]) for run in runs),
        "case_retry_count": sum(int(run.get("case_retry_count", 0)) for run in runs),
        "case_retries": [
            retry for run in runs for retry in run.get("case_retries", [])
        ],
        "all_solves_optimal": all(bool(run["all_solves_optimal"]) for run in runs),
        "independent_validation_passed": all(
            bool(run["independent_validation_passed"]) for run in runs
        ),
        "maximum_validation_residual": max(
            float(run["maximum_validation_residual"]) for run in runs
        ),
        "records_path": str(records_path),
        "records_sha256": _file_sha256(records_path),
        "published_price_rows": _published_price_rows(published),
        "parity": parity,
    }
    combined: dict[str, Any] = {
        key: first[key]
        for key in (
            "schema_version",
            "profile",
            "source_name",
            "source_sha256",
            "input_schema",
            "environment",
            "versions",
            "validation_tolerance",
        )
    }
    combined.update(
        {
            "expected_case_count": expected,
            "selected_profiles": [profile],
            "shards": [str(path) for path in args.shard],
            "runs": [run],
        }
    )
    _finish_payload(combined)
    _write(args.output, combined)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "profile": profile,
                "case_count": case_count,
                "all_solves_optimal": run["all_solves_optimal"],
                "independent_validation_passed": run[
                    "independent_validation_passed"
                ],
                "maximum_validation_residual": run[
                    "maximum_validation_residual"
                ],
                "records_sha256": run["records_sha256"],
            },
            sort_keys=True,
        )
    )


def _validate(payloads: list[dict[str, Any]], runs: list[dict[str, Any]]) -> None:
    if any(len(payload["runs"]) != 1 for payload in payloads):
        raise ValueError("each shard must contain exactly one solver run")
    identity = (
        "schema_version",
        "source_name",
        "source_sha256",
        "input_schema",
        "environment",
        "validation_tolerance",
    )
    first = payloads[0]
    if any(
        any(payload[key] != first[key] for key in identity) for payload in payloads[1:]
    ):
        raise ValueError("shard provenance differs")
    if len({run["profile"] for run in runs}) != 1:
        raise ValueError("shards use different solver profiles")
    if not all(run.get("completed") for run in runs):
        raise ValueError("cannot merge an incomplete shard")


def _record_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record["case_id"]),
        str(record["date_time"]),
        str(record["trading_period"]),
    )


def _accumulate_published(
    record: dict[str, Any],
    energy_numerator: dict[tuple[str, str], float],
    reserve_numerator: dict[tuple[str, str, str], float],
    total_seconds: dict[str, float],
    date_time: dict[str, str],
    *,
    energy_lower_numerator: dict[tuple[str, str], float] | None = None,
    energy_upper_numerator: dict[tuple[str, str], float] | None = None,
    energy_interval_keys: set[tuple[str, str]] | None = None,
    reserve_lower_numerator: dict[tuple[str, str, str], float] | None = None,
    reserve_upper_numerator: dict[tuple[str, str, str], float] | None = None,
    reserve_interval_keys: set[tuple[str, str, str]] | None = None,
) -> None:
    period = record["trading_period"]
    seconds = float.fromhex(record["publication_seconds"])
    date_time.setdefault(period, record["date_time"])
    if seconds <= 0.0:
        return
    total_seconds[period] += seconds
    intervals = {
        row["node"]: json.loads(raw)
        for row in record.get("reports", {}).get("node", ())
        if (raw := row.get("price_interval", ""))
    }
    for key, value in record["prices"]["node"]:
        energy_key = (period, key[-1])
        price = float.fromhex(value)
        energy_numerator[energy_key] += price * seconds
        if energy_lower_numerator is None or energy_upper_numerator is None:
            continue
        bounds = intervals.get(key[-1], (price, price))
        if (
            not isinstance(bounds, list | tuple)
            or len(bounds) != 2
            or float(bounds[0]) > float(bounds[1])
        ):
            raise ValueError(f"invalid node price interval for {key[-1]}")
        energy_lower_numerator[energy_key] += float(bounds[0]) * seconds
        energy_upper_numerator[energy_key] += float(bounds[1]) * seconds
        if key[-1] in intervals and energy_interval_keys is not None:
            energy_interval_keys.add(energy_key)
    reserve_intervals = {
        tuple(key): tuple(float.fromhex(bound) for bound in bounds)
        for key, bounds in record.get("price_intervals", {}).get("reserve", ())
    }
    for key, value in record["prices"]["reserve"]:
        reserve_key = (period, key[-2], key[-1])
        price = float.fromhex(value)
        reserve_numerator[reserve_key] += price * seconds
        if reserve_lower_numerator is None or reserve_upper_numerator is None:
            continue
        bounds = reserve_intervals.get(tuple(key), (price, price))
        reserve_lower_numerator[reserve_key] += bounds[0] * seconds
        reserve_upper_numerator[reserve_key] += bounds[1] * seconds
        if tuple(key) in reserve_intervals and reserve_interval_keys is not None:
            reserve_interval_keys.add(reserve_key)


if __name__ == "__main__":
    main()
