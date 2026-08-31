"""Enumerate the exact Gate 12 v5 shortfall-transfer population."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from tools.gate12.evidence import (
    EXPECTED_AFFECTED_INTERVALS,
    EXPECTED_TRADING_DATES,
    EvidenceContractError,
)
from tools.gate12.historical_population import (
    HISTORICAL_EXECUTION_PROFILE,
    GamsTransferCaseIndexLoader,
    HistoricalAffectedManifestBuilder,
    HistoricalInputInventory,
    HistoricalPopulationCheckpointStore,
    HistoricalPopulationRunner,
    HistoricalPopulationWorkspace,
    HistoricalTargetedScipPatcher,
    HistoricalVspdSourcePatcher,
    SubprocessHistoricalGamsExecutor,
)

REFERENCE_COMMIT = "3360a91ebd48f2e3cbb52a5e6766d893011054be"


@dataclass(frozen=True)
class HistoricalEnumerationOutcome:
    """Separate shard execution success from full-population qualification."""

    execution_scope: str
    shard_complete: bool
    population_passed: bool

    @property
    def execution_passed(self) -> bool:
        return self.shard_complete if self.execution_scope == "shard" else self.population_passed

    @property
    def emit_manifest(self) -> bool:
        return self.execution_scope == "population" and self.population_passed

    @classmethod
    def evaluate(
        cls,
        *,
        execution_scope: str,
        inventory_count: int,
        checkpoint_count: int,
        affected_interval_count: int,
    ) -> HistoricalEnumerationOutcome:
        if execution_scope not in {"population", "shard"}:
            raise EvidenceContractError(
                "REQ-G12-HISTORICAL: invalid enumeration execution scope"
            )
        shard_complete = checkpoint_count == inventory_count
        population_passed = bool(
            inventory_count == EXPECTED_TRADING_DATES
            and checkpoint_count == EXPECTED_TRADING_DATES
            and affected_interval_count == EXPECTED_AFFECTED_INTERVALS
        )
        return cls(
            execution_scope=execution_scope,
            shard_complete=shard_complete,
            population_passed=population_passed,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--gams-executable", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument(
        "--network-license-attempts",
        type=int,
        default=6,
        help="Maximum attempts for the specific transient GAMS network-licence failure.",
    )
    parser.add_argument(
        "--network-license-retry-seconds",
        type=float,
        default=300.0,
        help="Delay between transient GAMS network-licence attempts.",
    )
    parser.add_argument(
        "--tight-scip-case-id",
        help=(
            "Load the separately hash-addressed SCIP feastol 1e-10 option "
            "file for this numeric case ID only."
        ),
    )
    parser.add_argument(
        "--execution-scope",
        choices=("population", "shard"),
        default="population",
        help=(
            "Use shard only for a partial inventory; it reports execution "
            "success but can never emit or claim the population manifest."
        ),
    )
    return parser


def _verify_reference(source_tree: Path) -> None:
    completed = subprocess.run(
        ["git", "-C", str(source_tree), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or completed.stdout.strip() != REFERENCE_COMMIT:
        raise EvidenceContractError(
            "REQ-G12-HISTORICAL: source tree is not pinned vSPD v5.0.2"
        )


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    source_tree = args.source_tree.resolve()
    work_directory = args.work_directory.resolve()
    _verify_reference(source_tree)
    patcher = (
        HistoricalTargetedScipPatcher(args.tight_scip_case_id)
        if args.tight_scip_case_id
        else HistoricalVspdSourcePatcher()
    )
    metadata = work_directory / "patch-evidence.json"
    workspace = (
        HistoricalPopulationWorkspace.open(work_directory)
        if metadata.is_file()
        else HistoricalPopulationWorkspace.prepare(
            source_tree=source_tree,
            root=work_directory,
            patcher=patcher,
        )
    )
    if workspace.patch_evidence.profile != patcher.profile:
        raise EvidenceContractError(
            "REQ-G12-HISTORICAL: workspace patch profile does not match CLI"
        )
    inventory = HistoricalInputInventory.load(args.inventory.resolve())
    runner = HistoricalPopulationRunner(
        programs=workspace.programs,
        input_root=args.input_root.resolve(),
        inventory=inventory,
        system_directory=args.system_directory.resolve(),
        gams_executable=args.gams_executable.resolve(),
        patch_evidence=workspace.patch_evidence,
        checkpoint_store=HistoricalPopulationCheckpointStore(
            work_directory / "checkpoints"
        ),
        executor=SubprocessHistoricalGamsExecutor(
            network_license_attempts=args.network_license_attempts,
            network_license_retry_seconds=args.network_license_retry_seconds,
        ),
    )
    checkpoints = runner.run()
    per_date = {
        checkpoint.trading_date: checkpoint.affected_case_count
        for checkpoint in checkpoints
    }
    affected_count = sum(per_date.values())
    outcome = HistoricalEnumerationOutcome.evaluate(
        execution_scope=args.execution_scope,
        inventory_count=len(inventory.artifacts),
        checkpoint_count=len(checkpoints),
        affected_interval_count=affected_count,
    )
    summary = {
        "schema_version": 1,
        "reference_commit": REFERENCE_COMMIT,
        "patch_profile": workspace.patch_evidence.profile,
        "patch_sha256": workspace.patch_evidence.logical_sha256,
        "execution_profile": HISTORICAL_EXECUTION_PROFILE,
        "execution_scope": outcome.execution_scope,
        "trading_date_count": len(checkpoints),
        "affected_interval_count": affected_count,
        "per_date": per_date,
        "checkpoint_sha256": {
            checkpoint.trading_date: checkpoint.logical_sha256
            for checkpoint in checkpoints
        },
        "shard_complete": outcome.shard_complete,
        "population_passed": outcome.population_passed,
        "passed": outcome.execution_passed,
    }
    (work_directory / "population-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if outcome.emit_manifest:
        index_loader = GamsTransferCaseIndexLoader()
        case_indices = {
            artifact.trading_date: index_loader.load(
                args.input_root.resolve()
                / artifact.trading_date[:4]
                / f"Pricing_{artifact.trading_date}.gdx",
                args.system_directory.resolve(),
            )
            for artifact in inventory.artifacts
        }
        manifest = HistoricalAffectedManifestBuilder().build(
            checkpoints=checkpoints,
            inventory=inventory,
            case_indices=case_indices,
            source_release=(
                "https://github.com/ElectricityAuthority/vSPD/releases/tag/v5.0.4"
            ),
            reference_commit=REFERENCE_COMMIT,
        )
        manifest_payload = {
            "schema_version": 1,
            "source_release": manifest.source_release,
            "reference_commit": manifest.reference_commit,
            "execution_profile": HISTORICAL_EXECUTION_PROFILE,
            "identities": [asdict(identity) for identity in manifest.identities],
        }
        (work_directory / "interval-identity-manifest.json").write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, sort_keys=True))
    return 0 if outcome.execution_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
