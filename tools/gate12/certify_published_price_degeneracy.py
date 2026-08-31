"""Run and persist qualified alternative published-price evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.gate12.published_price_degeneracy import (
    PublishedPriceDegeneracyResultStore,
    PublishedPriceDegeneracyRunner,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--reference-bundle-root", type=Path, required=True)
    parser.add_argument("--candidate-bundle-root", type=Path, required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    result = PublishedPriceDegeneracyRunner(
        input_path=args.input.resolve(),
        system_directory=args.system_directory.resolve(),
        reference_root=args.reference_bundle_root.resolve(),
        candidate_root=args.candidate_bundle_root.resolve(),
        run_root=args.run_root.resolve(),
    ).run(args.trading_date)
    target = PublishedPriceDegeneracyResultStore().write(
        result, args.output.resolve()
    )
    print(
        json.dumps(
            {
                "trading_date": result.trading_date,
                "passed": result.passed,
                "period_count": len(result.periods),
                "logical_sha256": result.logical_sha256,
                "output": str(target),
            },
            sort_keys=True,
        )
    )
    return int(not result.passed)


if __name__ == "__main__":
    raise SystemExit(main())
