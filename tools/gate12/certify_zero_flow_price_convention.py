"""Create a hash-bound zero-flow price and publication certificate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.gate12.zero_flow_price_convention import (
    ZeroFlowPriceConventionResultStore,
)
from tools.gate12.zero_flow_price_runner import ZeroFlowPriceConventionRunner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reference-result-gdx", type=Path, required=True)
    parser.add_argument("--system-directory", type=Path, required=True)
    parser.add_argument("--reference-bundle-root", type=Path, required=True)
    parser.add_argument("--candidate-bundle-root", type=Path, required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = ZeroFlowPriceConventionRunner(
        source_path=args.input,
        reference_result_gdx=args.reference_result_gdx,
        system_directory=args.system_directory,
        reference_root=args.reference_bundle_root,
        candidate_root=args.candidate_bundle_root,
    ).run(args.trading_date)
    target = ZeroFlowPriceConventionResultStore().write(result, args.output)
    print(
        json.dumps(
            {
                "output": str(target),
                "passed": result.passed,
                "case_count": len(result.cases),
                "certified_bus_count": sum(
                    len(case.certified_bus_identities) for case in result.cases
                ),
                "certified_node_count": sum(
                    len(case.certified_node_identities) for case in result.cases
                ),
                "publication_count": len(result.publications),
                "logical_sha256": result.logical_sha256,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
