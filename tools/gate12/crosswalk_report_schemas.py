"""Crosswalk Authority and PySPD report schemas for one paired Gate 12 date."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.gate12.report_crosswalk import (
    ReportSchemaCrosswalkResultStore,
    ReportSchemaCrosswalkRunner,
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
    result = ReportSchemaCrosswalkRunner(
        reference_root=args.reference_bundle_root.resolve(),
        candidate_root=args.candidate_bundle_root.resolve(),
    ).compare(args.trading_date)
    target = ReportSchemaCrosswalkResultStore().write(result, args.output.resolve())
    print(
        json.dumps(
            {
                "trading_date": result.trading_date,
                "passed": result.passed,
                "unmapped_reference_field_count": result.unmapped_reference_field_count,
                "unmapped_candidate_field_count": result.unmapped_candidate_field_count,
                "logical_sha256": result.logical_sha256,
                "output": str(target),
            },
            sort_keys=True,
        )
    )
    return int(not result.passed)


if __name__ == "__main__":
    raise SystemExit(main())
