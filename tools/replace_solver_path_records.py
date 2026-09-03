"""Replace targeted records in a complete solver-path stream and reaggregate it."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable
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
from tools.merge_solver_path_shards import _accumulate_published


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--replacement", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    base = json.loads(arguments.base.read_text(encoding="utf-8"))
    replacement = json.loads(arguments.replacement.read_text(encoding="utf-8"))
    base_run, replacement_run = _compatible_runs(base, replacement)
    replacement_records = _load_unique_records(Path(replacement_run["records_path"]))

    profile = base_run["profile"]
    records_path = _records_path(arguments.output, profile)
    records_path.parent.mkdir(parents=True, exist_ok=True)
    statistics = _replace_stream(
        Path(base_run["records_path"]),
        records_path,
        replacement_records,
        profile=profile,
    )

    run = dict(base_run)
    run.update(
        {
            "case_count": statistics["case_count"],
            "solve_calls": statistics["solve_calls"],
            "all_solves_optimal": statistics["all_solves_optimal"],
            "independent_validation_passed": statistics[
                "independent_validation_passed"
            ],
            "maximum_validation_residual": statistics[
                "maximum_validation_residual"
            ],
            "records_path": str(records_path),
            "records_sha256": _file_sha256(records_path),
            "published_price_rows": statistics["published_price_rows"],
            "parity": statistics["parity"],
            "replaced_case_count": len(replacement_records),
            "performance_inherited_from_base": True,
        }
    )
    payload = {
        key: value
        for key, value in base.items()
        if key not in {"runs", "logical_sha256"}
    }
    payload["runs"] = [run]
    payload["record_substitution"] = {
        "base_summary": str(arguments.base),
        "base_summary_sha256": _file_sha256(arguments.base),
        "replacement_summary": str(arguments.replacement),
        "replacement_summary_sha256": _file_sha256(arguments.replacement),
        "case_ids": sorted(replacement_records),
    }
    _finish_payload(payload)
    _write(arguments.output, payload)
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "records_path": str(records_path),
                "records_sha256": run["records_sha256"],
                "case_count": run["case_count"],
                "solve_calls": run["solve_calls"],
                "replaced_case_count": run["replaced_case_count"],
            },
            sort_keys=True,
        )
    )


def _compatible_runs(
    base: dict[str, Any], replacement: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(base.get("runs", ())) != 1 or len(replacement.get("runs", ())) != 1:
        raise ValueError("base and replacement must each contain exactly one run")
    base_run, replacement_run = base["runs"][0], replacement["runs"][0]
    for field in ("source_sha256", "input_schema"):
        if base.get(field) != replacement.get(field):
            raise ValueError(f"incompatible {field}")
    if base_run["profile"] != replacement_run["profile"]:
        raise ValueError("incompatible solver profiles")
    if not base_run.get("completed") or not replacement_run.get("completed"):
        raise ValueError("both runs must be complete for their declared inventory")
    return base_run, replacement_run


def _load_unique_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            case_id = record["case_id"]
            if case_id in records:
                raise ValueError(f"duplicate replacement case: {case_id}")
            records[case_id] = record
    if not records:
        raise ValueError("replacement stream is empty")
    return records


def _replace_stream(
    source_path: Path,
    target_path: Path,
    replacements: dict[str, dict[str, Any]],
    *,
    profile: str,
) -> dict[str, Any]:
    used: set[str] = set()
    energy_numerator: dict[tuple[str, str], float] = defaultdict(float)
    reserve_numerator: dict[tuple[str, str, str], float] = defaultdict(float)
    total_seconds: dict[str, float] = defaultdict(float)
    date_time: dict[str, str] = {}
    parity = _empty_parity(profile)
    parity["comparison_available"] = True
    parity["self_reference"] = True
    case_count = solve_calls = 0
    optimal = validation_passed = True
    maximum_residual = 0.0

    def accumulate(record: dict[str, Any]) -> None:
        _accumulate_published(
            record,
            energy_numerator,
            reserve_numerator,
            total_seconds,
            date_time,
        )
        _update_parity(parity, record, record)

    with source_path.open(encoding="utf-8") as source, target_path.open(
        "w", encoding="utf-8"
    ) as target:
        _replace_lines(
            source,
            target,
            replacements,
            used,
            accumulator=accumulate,
        )
    if used != set(replacements):
        missing = sorted(set(replacements) - used)
        raise ValueError("replacement cases absent from base: " + ", ".join(missing))
    with target_path.open(encoding="utf-8") as records:
        for line in records:
            record = json.loads(line)
            case_count += 1
            solve_calls += int(record["solve_count"])
            optimal = optimal and bool(record["optimal"])
            validation_passed = validation_passed and bool(
                record["validation_passed"]
            )
            maximum_residual = max(
                maximum_residual, float(record["maximum_validation_residual"])
            )
    _finalize_parity(parity)
    published = SimpleNamespace(
        energy={
            key: round(value / total_seconds[key[0]], 5)
            for key, value in energy_numerator.items()
        },
        reserve={
            key: round(value / total_seconds[key[0]], 5)
            for key, value in reserve_numerator.items()
        },
        total_seconds=total_seconds,
        date_time=date_time,
    )
    return {
        "case_count": case_count,
        "solve_calls": solve_calls,
        "all_solves_optimal": optimal,
        "independent_validation_passed": validation_passed,
        "maximum_validation_residual": maximum_residual,
        "published_price_rows": _published_price_rows(published),
        "parity": parity,
    }


def _replace_lines(
    source: TextIO,
    target: TextIO,
    replacements: dict[str, dict[str, Any]],
    used: set[str],
    *,
    accumulator: Callable[[dict[str, Any]], None],
) -> None:
    seen: set[str] = set()
    for line in source:
        record = json.loads(line)
        case_id = record["case_id"]
        if case_id in seen:
            raise ValueError(f"duplicate base case: {case_id}")
        seen.add(case_id)
        if case_id in replacements:
            record = replacements[case_id]
            used.add(case_id)
        accumulator(record)
        target.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
