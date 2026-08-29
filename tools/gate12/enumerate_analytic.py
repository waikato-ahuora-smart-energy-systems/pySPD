"""Screen Gate 12 population candidates with pinned first-loop RTD algebra."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tools.gate12.analytic_population import HistoricalAnalyticDayEnumerator
from tools.gate12.historical_population import HistoricalInputInventory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser


def _logical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    input_root = args.input_root.resolve()
    system_directory = args.system_directory.resolve()
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    inventory = HistoricalInputInventory.load(args.inventory.resolve())
    enumerator = HistoricalAnalyticDayEnumerator()
    daily_results = []
    for position, artifact in enumerate(inventory.artifacts, start=1):
        source = (
            input_root
            / artifact.trading_date[:4]
            / f"Pricing_{artifact.trading_date}.gdx"
        )
        result = enumerator.enumerate(
            artifact=artifact,
            path=source,
            system_directory=system_directory,
        )
        daily_results.append(result)
        print(
            f"[{position:03d}/{len(inventory.artifacts)}] "
            f"{artifact.trading_date}: {len(result.candidates)} candidates",
            flush=True,
        )

    candidate_count = sum(len(result.candidates) for result in daily_results)
    screen_payload: dict[str, Any] = {
        "schema_version": 1,
        "method": "dailymode0 first-loop RTD algebraic dead-node candidate screen",
        "trading_date_count": len(daily_results),
        "candidate_interval_count": candidate_count,
        "declared_interval_count": 546,
        "declared_count_gap": 546 - candidate_count,
        "qualifies_exact_population": False,
        "per_date": {
            result.trading_date: {
                "source_sha256": result.source_sha256,
                "selected_rtd_case_count": result.selected_rtd_case_count,
                "candidate_interval_count": len(result.candidates),
            }
            for result in daily_results
        },
        "node_evidence": [
            {
                **asdict(record.identity),
                "affected_shortfall_mw": record.affected_shortfall_mw,
            }
            for result in daily_results
            for record in result.candidates
        ],
    }
    screen_payload["logical_sha256"] = _logical_sha256(screen_payload)
    _write_json(output_directory / "analytic-candidate-screen.json", screen_payload)
    print(
        json.dumps(
            {
                "passed": False,
                "candidate_interval_count": candidate_count,
                "declared_count_gap": 546 - candidate_count,
                "diagnostic": (
                    "candidate screen cannot qualify the disclosed dailymode1 "
                    "population; solved enumeration is required"
                ),
                "output": str(output_directory / "analytic-candidate-screen.json"),
            },
            sort_keys=True,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
