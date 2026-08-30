"""Write a quantified path-level diff for one paired Gate 12 replay date."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.gate12.canonical_diff import (
    CanonicalBundleDiffer,
    CanonicalBundleDifferenceStore,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-bundle-root", type=Path, required=True)
    parser.add_argument("--candidate-bundle-root", type=Path, required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    difference = CanonicalBundleDiffer(
        reference_root=args.reference_bundle_root.resolve(),
        candidate_root=args.candidate_bundle_root.resolve(),
    ).compare(args.trading_date)
    target = CanonicalBundleDifferenceStore().write(difference, args.output.resolve())
    print(
        json.dumps(
            {
                "trading_date": difference.trading_date,
                "identical": difference.identical,
                "changed_surface_count": difference.changed_surface_count,
                "unresolved_difference_count": (difference.unresolved_difference_count),
                "maximum_absolute_error": difference.maximum_absolute_error.hex(),
                "logical_sha256": difference.logical_sha256,
                "output": str(target),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
