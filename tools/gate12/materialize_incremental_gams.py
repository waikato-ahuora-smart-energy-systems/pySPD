"""Materialize pinned-GAMS replay bundles from available discovery checkpoints."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from tools.gate12.historical_population import (
    GamsTransferCaseIndexLoader,
    HistoricalInputInventory,
    HistoricalPopulationCheckpointStore,
)
from tools.gate12.incremental_replay import IncrementalDiscoveryFeed
from tools.gate12.replay_artifacts import (
    GamsReplayBundleProducer,
    IncrementalReplayBundleCoordinator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-checkpoints", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--gams-executable", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--maximum-new-dates", type=int)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    if args.poll_seconds <= 0.0 or args.poll_seconds > 60.0:
        raise ValueError("poll-seconds must lie in (0, 60]")
    inventory = HistoricalInputInventory.load(args.inventory.resolve())
    feed = IncrementalDiscoveryFeed(
        inventory=inventory,
        input_root=args.input_root.resolve(),
        system_directory=args.system_directory.resolve(),
        discovery_store=HistoricalPopulationCheckpointStore(
            args.discovery_checkpoints.resolve()
        ),
        index_loader=GamsTransferCaseIndexLoader(),
    )
    coordinator = IncrementalReplayBundleCoordinator(
        feed=feed,
        producer=GamsReplayBundleProducer(
            bundle_root=args.bundle_root.resolve(),
            run_root=args.run_root.resolve(),
            source_tree=args.source_tree.resolve(),
            gams_executable=args.gams_executable.resolve(),
        ),
    )
    while True:
        summary = coordinator.run_available(maximum_new_dates=args.maximum_new_dates)
        print(json.dumps(asdict(summary), sort_keys=True), flush=True)
        complete = bool(
            summary.available_date_count == len(inventory.artifacts)
            and summary.bundle_count == len(inventory.artifacts)
        )
        if complete or not args.watch:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
