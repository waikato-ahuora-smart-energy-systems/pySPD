"""Compare mapped Authority/PySPD report rows for one paired Gate 12 date."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.gate12.report_row_parity import (
    ReportRowParityResultStore,
    ReportRowParityRunner,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-bundle-root", type=Path, required=True)
    parser.add_argument("--candidate-bundle-root", type=Path, required=True)
    parser.add_argument("--schema-crosswalk", type=Path, required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    result = ReportRowParityRunner(
        reference_root=args.reference_bundle_root.resolve(),
        candidate_root=args.candidate_bundle_root.resolve(),
        schema_crosswalk=args.schema_crosswalk.resolve(),
    ).compare(args.trading_date)
    target = ReportRowParityResultStore().write(result, args.output.resolve())
    payload = result.to_dict()
    print(
        json.dumps(
            {
                "trading_date": result.trading_date,
                "passed": result.passed,
                "missing_identity_count": payload["missing_identity_count"],
                "extra_identity_count": payload["extra_identity_count"],
                "above_precision_count": payload["above_precision_count"],
                "unimplemented_table_count": payload["unimplemented_table_count"],
                "logical_sha256": result.logical_sha256,
                "output": str(target),
            },
            sort_keys=True,
        )
    )
    return int(not result.passed)


if __name__ == "__main__":
    raise SystemExit(main())
