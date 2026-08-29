"""Screen Gate 12 population candidates with pinned first-loop RTD algebra."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tools.gate12.analytic_population import (
    HistoricalAnalyticDayEnumerator,
    HistoricalAnalyticPopulationEvidenceBuilder,
)
from tools.gate12.evidence import EvidenceContractError
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
            f"{artifact.trading_date}: {len(result.affected)} affected",
            flush=True,
        )

    candidate_count = sum(len(result.affected) for result in daily_results)
    screen_payload: dict[str, Any] = {
        "schema_version": 1,
        "method": "dailymode0 first-loop RTD algebraic dead-node lower bound",
        "trading_date_count": len(daily_results),
        "candidate_interval_count": candidate_count,
        "declared_interval_count": 546,
        "unresolved_interval_count": 546 - candidate_count,
        "qualifies_exact_population": False,
        "per_date": {
            result.trading_date: {
                "source_sha256": result.source_sha256,
                "selected_rtd_case_count": result.selected_rtd_case_count,
                "candidate_interval_count": len(result.affected),
            }
            for result in daily_results
        },
        "node_evidence": [
            {
                **asdict(record.identity),
                "affected_shortfall_mw": record.affected_shortfall_mw,
            }
            for result in daily_results
            for record in result.affected
        ],
    }
    screen_payload["logical_sha256"] = _logical_sha256(screen_payload)
    _write_json(output_directory / "analytic-candidate-screen.json", screen_payload)
    try:
        evidence = HistoricalAnalyticPopulationEvidenceBuilder().build(
            daily_results=tuple(daily_results), inventory=inventory
        )
    except EvidenceContractError as error:
        print(
            json.dumps(
                {
                    "passed": False,
                    "candidate_interval_count": candidate_count,
                    "unresolved_interval_count": 546 - candidate_count,
                    "diagnostic": str(error),
                    "output": str(
                        output_directory / "analytic-candidate-screen.json"
                    ),
                },
                sort_keys=True,
            )
        )
        return 1
    manifest_payload = {
        "schema_version": 1,
        "source_release": evidence.manifest.source_release,
        "reference_commit": evidence.manifest.reference_commit,
        "identities": [asdict(identity) for identity in evidence.manifest.identities],
    }
    manifest_payload["logical_sha256"] = _logical_sha256(manifest_payload)
    _write_json(
        output_directory / "interval-identity-manifest.json", manifest_payload
    )

    qualification_payload: dict[str, Any] = {
        "schema_version": 1,
        "method": {
            "profile": "pinned-v5.0.2-first-loop-rtd-algebra",
            "reference_commit": evidence.manifest.reference_commit,
            "source_equations": "vSPDsolve.gms:878-919,1217-1248",
            "material_shortfall_mw": 1e-6,
            "interpretation": (
                "exact reconstruction of the first-loop required-load equations; "
                "not a relaxed dispatch solve"
            ),
        },
        "trading_date_count": len(evidence.daily_results),
        "affected_interval_count": len(evidence.manifest.identities),
        "selected_rtd_case_count": sum(
            result.selected_rtd_case_count for result in evidence.daily_results
        ),
        "per_date": {
            result.trading_date: {
                "source_sha256": result.source_sha256,
                "selected_rtd_case_count": result.selected_rtd_case_count,
                "affected_interval_count": len(result.affected),
            }
            for result in evidence.daily_results
        },
        "node_evidence": [
            {
                **asdict(record.identity),
                "affected_shortfall_mw": record.affected_shortfall_mw,
            }
            for result in evidence.daily_results
            for record in result.affected
        ],
        "manifest_logical_sha256": manifest_payload["logical_sha256"],
        "passed": True,
    }
    qualification_payload["logical_sha256"] = _logical_sha256(
        qualification_payload
    )
    _write_json(
        output_directory / "analytic-population-qualification.json",
        qualification_payload,
    )
    print(
        json.dumps(
            {
                "passed": True,
                "trading_date_count": len(evidence.daily_results),
                "affected_interval_count": len(evidence.manifest.identities),
                "output_directory": str(output_directory),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
