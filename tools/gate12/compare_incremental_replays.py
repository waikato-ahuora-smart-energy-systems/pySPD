"""Compare available canonical GAMS and PySPD replay bundles incrementally."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from tools.gate12.historical_population import (
    GamsTransferCaseIndexLoader,
    HistoricalInputInventory,
    HistoricalPopulationCheckpointStore,
)
from tools.gate12.incremental_replay import (
    IncrementalGate12Coordinator,
    IncrementalParityCheckpointStore,
)
from tools.gate12.replay_artifacts import ExactCanonicalDirectoryParityProcessor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-checkpoints", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--reference-bundle-root", type=Path, required=True)
    parser.add_argument("--candidate-bundle-root", type=Path, required=True)
    parser.add_argument("--parity-checkpoints", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    inventory = HistoricalInputInventory.load(args.inventory.resolve())
    summary = IncrementalGate12Coordinator(
        inventory=inventory,
        input_root=args.input_root.resolve(),
        system_directory=args.system_directory.resolve(),
        discovery_store=HistoricalPopulationCheckpointStore(
            args.discovery_checkpoints.resolve()
        ),
        parity_store=IncrementalParityCheckpointStore(
            args.parity_checkpoints.resolve()
        ),
        index_loader=GamsTransferCaseIndexLoader(),
        processor=ExactCanonicalDirectoryParityProcessor(
            reference_root=args.reference_bundle_root.resolve(),
            candidate_root=args.candidate_bundle_root.resolve(),
        ),
    ).run_available()
    print(json.dumps(asdict(summary), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
