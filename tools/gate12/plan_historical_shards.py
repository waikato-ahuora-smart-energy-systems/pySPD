"""Plan deterministic balanced shards for Gate 12 GAMS enumeration."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from tools.gate12.historical_population import (
    HistoricalInputInventory,
    HistoricalPopulationShardPlanner,
)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    args = parser.parse_args(arguments)
    inventory = HistoricalInputInventory.load(args.inventory.resolve())
    shards = HistoricalPopulationShardPlanner().plan(
        inventory, shard_count=args.shard_count
    )
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    summary = []
    for index, shard in enumerate(shards):
        payload = {
            "schema_version": 1,
            "artifact_count": len(shard.artifacts),
            "artifacts": [asdict(artifact) for artifact in shard.artifacts],
        }
        path = output_directory / f"inventory-{index:02d}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
        summary.append(
            {
                "shard": index,
                "artifact_count": len(shard.artifacts),
                "size_bytes": sum(item.size_bytes for item in shard.artifacts),
                "inventory": str(path),
            }
        )
    print(json.dumps({"shards": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
