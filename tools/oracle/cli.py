"""Command-line interface for the vSPD oracle harness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from tools.oracle.vspd import (
    BaselineComparison,
    CplexOracleProfile,
    ObjectiveBaseline,
    ScipHighsPricingProfile,
    ScipSmokeProfile,
    VspdCase,
    VspdListingParser,
    VspdRunner,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare = subparsers.add_parser("compare", help="compare a listing to a baseline")
    compare.add_argument("--listing", type=Path, required=True)
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--absolute-tolerance", type=float, default=0.01)
    compare.add_argument("--relative-tolerance", type=float, default=1e-9)

    run = subparsers.add_parser("run", help="stage and run one vSPD case")
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--work-directory", type=Path, required=True)
    run.add_argument("--gams", type=Path, required=True)
    run.add_argument(
        "--profile",
        choices=("scip-smoke", "scip-highs-pricing", "cplex-oracle"),
        default="scip-smoke",
    )
    run.add_argument("--baseline", type=Path)
    run.add_argument("--absolute-tolerance", type=float, default=0.01)
    run.add_argument("--relative-tolerance", type=float, default=1e-9)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "compare":
        parsed = VspdListingParser().parse_file(arguments.listing)
        comparison = BaselineComparison.compare(
            actual=parsed.primary,
            expected=ObjectiveBaseline.load(arguments.baseline),
            absolute_tolerance=arguments.absolute_tolerance,
            relative_tolerance=arguments.relative_tolerance,
        )
        print(json.dumps(comparison.to_dict(), indent=2, sort_keys=True))
        return 0 if comparison.passed else 1

    profiles = {
        "scip-smoke": ScipSmokeProfile,
        "scip-highs-pricing": ScipHighsPricingProfile,
        "cplex-oracle": CplexOracleProfile,
    }
    profile = profiles[arguments.profile]()
    baseline = (
        ObjectiveBaseline.load(arguments.baseline) if arguments.baseline else None
    )
    result = VspdRunner().run(
        VspdCase(
            source_tree=arguments.source.resolve(),
            input_gdx=arguments.input.resolve(),
            work_directory=arguments.work_directory.resolve(),
            gams_executable=arguments.gams.resolve(),
            profile=profile,
        ),
        baseline=baseline,
        absolute_tolerance=arguments.absolute_tolerance,
        relative_tolerance=arguments.relative_tolerance,
    )
    payload = json.loads(result.evidence.read_text())
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not result.parsed.all_optimal:
        return 1
    return 0 if result.comparison is None or result.comparison.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
