"""Materialize hash-bound, prefix-complete PySPD replay configurations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pyspd.application import PORTABLE_SOLVER_PROFILE
from pyspd.reserve.data import RESERVE_FORMULATION_ID
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import (
    GamsTransferCaseIndexLoader,
    HistoricalGdxCaseIndex,
    HistoricalInputInventory,
)
from tools.gate12.replay import (
    HistoricalAffectedManifestLoader,
    HistoricalAffectedReplayPlanner,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser


class HistoricalReplaySourceVerifier:
    """Re-hash every replay input before loading its canonical case index."""

    def verify_and_index(
        self,
        *,
        inventory: HistoricalInputInventory,
        input_root: Path,
        system_directory: Path,
    ) -> dict[str, HistoricalGdxCaseIndex]:
        loader = GamsTransferCaseIndexLoader()
        output: dict[str, HistoricalGdxCaseIndex] = {}
        for artifact in inventory.artifacts:
            source = (
                input_root
                / artifact.trading_date[:4]
                / f"Pricing_{artifact.trading_date}.gdx"
            )
            try:
                size = source.stat().st_size
            except OSError as error:
                raise EvidenceContractError(
                    "REQ-G12-REPLAY: governed replay source is unavailable"
                ) from error
            if size != artifact.size_bytes or _file_sha256(source) != artifact.sha256:
                raise EvidenceContractError(
                    "REQ-G12-REPLAY: governed replay source hash or size mismatch"
                )
            output[artifact.trading_date] = loader.load(source, system_directory)
        return output


class HistoricalReplayPlanWriter:
    """Atomically write the plan, per-date application configs, and hash index."""

    def write(
        self,
        *,
        plan_payload: dict[str, object],
        inventory: HistoricalInputInventory,
        input_root: Path,
        system_directory: Path,
        output_directory: Path,
        manifest_sha256: str,
        inventory_sha256: str,
    ) -> None:
        if output_directory.exists():
            raise EvidenceContractError(
                "REQ-G12-REPLAY: replay plan output directory already exists"
            )
        temporary = output_directory.with_name(output_directory.name + ".tmp")
        if temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-REPLAY: replay plan temporary directory already exists"
            )
        temporary.mkdir(parents=True)
        config_directory = temporary / "configs"
        config_directory.mkdir()
        runs_directory = output_directory / "runs"
        artifacts = {
            artifact.trading_date: artifact for artifact in inventory.artifacts
        }
        configuration_sha256: dict[str, str] = {}
        batches = plan_payload.get("batches")
        if not isinstance(batches, list):
            raise EvidenceContractError("REQ-G12-REPLAY: invalid replay plan payload")
        for raw_batch in batches:
            if not isinstance(raw_batch, dict):
                raise EvidenceContractError(
                    "REQ-G12-REPLAY: invalid replay batch payload"
                )
            trading_date = str(raw_batch["trading_date"])
            artifact = artifacts[trading_date]
            configuration: dict[str, object] = {
                "formulation_id": RESERVE_FORMULATION_ID,
                "input_path": str(
                    input_root
                    / trading_date[:4]
                    / f"Pricing_{trading_date}.gdx"
                ),
                "output_directory": str(runs_directory / trading_date),
                "source_sha256": artifact.sha256,
                "gams_system_directory": str(system_directory),
                "solver_profile": PORTABLE_SOLVER_PROFILE,
                "case_ids": raw_batch["case_ids"],
                "maximum_solve_loops": 5,
                "price_rounding_decimals": 5,
            }
            payload = _json_bytes(configuration)
            filename = f"{trading_date}.json"
            (config_directory / filename).write_bytes(payload)
            configuration_sha256[trading_date] = hashlib.sha256(payload).hexdigest()
        (temporary / "replay-plan.json").write_bytes(_json_bytes(plan_payload))
        index: dict[str, object] = {
            "schema_version": 1,
            "formulation_id": RESERVE_FORMULATION_ID,
            "solver_profile": PORTABLE_SOLVER_PROFILE,
            "manifest_file_sha256": manifest_sha256,
            "inventory_file_sha256": inventory_sha256,
            "replay_plan_logical_sha256": plan_payload["logical_sha256"],
            "configuration_sha256": configuration_sha256,
        }
        (temporary / "replay-index.json").write_bytes(_json_bytes(index))
        temporary.replace(output_directory)


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    manifest_path = args.manifest.resolve()
    inventory_path = args.inventory.resolve()
    try:
        raw_manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceContractError(
            "REQ-G12-REPLAY: unreadable affected manifest"
        ) from error
    if not isinstance(raw_manifest, dict):
        raise EvidenceContractError("REQ-G12-REPLAY: affected manifest must be an object")
    manifest = HistoricalAffectedManifestLoader().from_dict(raw_manifest)
    inventory = HistoricalInputInventory.load(inventory_path)
    input_root = args.input_root.resolve()
    system_directory = args.system_directory.resolve()
    indices = HistoricalReplaySourceVerifier().verify_and_index(
        inventory=inventory,
        input_root=input_root,
        system_directory=system_directory,
    )
    plan = HistoricalAffectedReplayPlanner().plan(
        manifest=manifest,
        inventory=inventory,
        case_indices=indices,
    )
    HistoricalReplayPlanWriter().write(
        plan_payload=plan.to_dict(),
        inventory=inventory,
        input_root=input_root,
        system_directory=system_directory,
        output_directory=args.output_directory.resolve(),
        manifest_sha256=_file_sha256(manifest_path),
        inventory_sha256=_file_sha256(inventory_path),
    )
    print(json.dumps(plan.to_dict(), sort_keys=True))
    return 0


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


if __name__ == "__main__":
    raise SystemExit(main())
