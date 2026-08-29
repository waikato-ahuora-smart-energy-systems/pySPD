"""Merge complete Gate 12 shard checkpoints into the exact population manifest."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import (
    HISTORICAL_EXECUTION_PROFILE,
    GamsTransferCaseIndexLoader,
    HistoricalAffectedManifestBuilder,
    HistoricalInputInventory,
    HistoricalPopulationCheckpoint,
    HistoricalPopulationCheckpointStore,
)

REFERENCE_COMMIT = "3360a91ebd48f2e3cbb52a5e6766d893011054be"
SOURCE_RELEASE = "https://github.com/ElectricityAuthority/vSPD/releases/tag/v5.0.4"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--shard-work-directory", type=Path, action="append", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(arguments)
    inventory = HistoricalInputInventory.load(args.inventory.resolve())
    stores = tuple(
        HistoricalPopulationCheckpointStore(path.resolve() / "checkpoints")
        for path in args.shard_work_directory
    )
    checkpoints: list[HistoricalPopulationCheckpoint] = []
    for artifact in inventory.artifacts:
        matches = tuple(
            checkpoint
            for store in stores
            if (checkpoint := store.load(artifact.trading_date)) is not None
        )
        if len(matches) != 1:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: expected exactly one shard checkpoint for "
                f"{artifact.trading_date}"
            )
        checkpoint = matches[0]
        if (
            checkpoint.source_sha256 != artifact.sha256
            or checkpoint.solver_profile != HISTORICAL_EXECUTION_PROFILE
        ):
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: shard checkpoint provenance mismatch"
            )
        checkpoints.append(checkpoint)

    input_root = args.input_root.resolve()
    system_directory = args.system_directory.resolve()
    loader = GamsTransferCaseIndexLoader()
    case_indices = {
        artifact.trading_date: loader.load(
            input_root
            / artifact.trading_date[:4]
            / f"Pricing_{artifact.trading_date}.gdx",
            system_directory,
        )
        for artifact in inventory.artifacts
    }
    manifest = HistoricalAffectedManifestBuilder().build(
        checkpoints=tuple(checkpoints),
        inventory=inventory,
        case_indices=case_indices,
        source_release=SOURCE_RELEASE,
        reference_commit=REFERENCE_COMMIT,
    )
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_payload: dict[str, object] = {
        "schema_version": 1,
        "source_release": manifest.source_release,
        "reference_commit": manifest.reference_commit,
        "execution_profile": HISTORICAL_EXECUTION_PROFILE,
        "identities": [asdict(identity) for identity in manifest.identities],
    }
    _write_json(output_directory / "interval-identity-manifest.json", manifest_payload)
    summary: dict[str, object] = {
        "schema_version": 1,
        "reference_commit": REFERENCE_COMMIT,
        "execution_profile": HISTORICAL_EXECUTION_PROFILE,
        "trading_date_count": len(checkpoints),
        "affected_interval_count": len(manifest.identities),
        "per_date": {
            checkpoint.trading_date: checkpoint.affected_case_count
            for checkpoint in checkpoints
        },
        "checkpoint_sha256": {
            checkpoint.trading_date: checkpoint.logical_sha256
            for checkpoint in checkpoints
        },
        "passed": True,
    }
    _write_json(output_directory / "population-summary.json", summary)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
