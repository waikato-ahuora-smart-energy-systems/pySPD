"""Validate one paired Gate 12 replay under the named semantic policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.gate12.bus_price_degeneracy import BusPriceDegeneracyResultStore
from tools.gate12.report_row_parity import ReportRowParityResultStore
from tools.gate12.semantic_parity import (
    SemanticReplayResultStore,
    SemanticReplayValidator,
)
from tools.gate12.zero_flow_price_convention import (
    ZeroFlowPriceConventionResultStore,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-bundle-root", type=Path, required=True)
    parser.add_argument("--candidate-bundle-root", type=Path, required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bus-price-certificate", type=Path)
    parser.add_argument("--zero-flow-price-certificate", type=Path)
    parser.add_argument("--report-row-parity", type=Path)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    certificate = (
        None
        if args.bus_price_certificate is None
        else BusPriceDegeneracyResultStore().load(args.bus_price_certificate.resolve())
    )
    result = SemanticReplayValidator(
        reference_root=args.reference_bundle_root.resolve(),
        candidate_root=args.candidate_bundle_root.resolve(),
        bus_price_certificate=certificate,
        zero_flow_price_certificate=(
            None
            if args.zero_flow_price_certificate is None
            else ZeroFlowPriceConventionResultStore().load(
                args.zero_flow_price_certificate.resolve()
            )
        ),
        report_row_parity=(
            None
            if args.report_row_parity is None
            else ReportRowParityResultStore().load(args.report_row_parity.resolve())
        ),
    ).compare(args.trading_date)
    target = SemanticReplayResultStore().write(result, args.output.resolve())
    print(
        json.dumps(
            {
                "trading_date": result.trading_date,
                "passed": result.passed,
                "failed_surface_count": result.failed_surface_count,
                "unresolved_difference_count": result.unresolved_difference_count,
                "logical_sha256": result.logical_sha256,
                "output": str(target),
            },
            sort_keys=True,
        )
    )
    return int(not result.passed)


if __name__ == "__main__":
    raise SystemExit(main())
