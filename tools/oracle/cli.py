"""Command-line interface for the vSPD oracle harness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from tools.oracle.vspd import (
    BaselineComparison,
    CplexOracleProfile,
    InstrumentationNeutralityComparison,
    ObjectiveBaseline,
    ScipHighsPricingProfile,
    ScipHighsPrimalBasisProfile,
    ScipSmokeProfile,
    VspdCase,
    VspdListingParser,
    VspdRunConfiguration,
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

    neutrality = subparsers.add_parser(
        "compare-neutrality",
        help="compare checkpoint-instrumented and checkpoint-disabled evidence",
    )
    neutrality.add_argument("--instrumented", type=Path, required=True)
    neutrality.add_argument("--control", type=Path, required=True)

    run = subparsers.add_parser("run", help="stage and run one vSPD case")
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--work-directory", type=Path, required=True)
    run.add_argument("--gams", type=Path, required=True)
    run.add_argument(
        "--profile",
        choices=(
            "scip-smoke",
            "scip-highs-pricing",
            "scip-highs-primal-basis",
            "cplex-oracle",
        ),
        default="scip-smoke",
    )
    run.add_argument("--baseline", type=Path)
    run.add_argument("--run-name")
    run.add_argument("--operation-mode", choices=("SPD", "AUD", "DPS"))
    run.add_argument("--daily-mode", type=int, choices=(0, 1))
    run.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="select an exact GDX case ID; repeat for multiple cases",
    )
    run.add_argument("--absolute-tolerance", type=float, default=0.01)
    run.add_argument("--relative-tolerance", type=float, default=1e-9)
    run.add_argument(
        "--no-state-evidence",
        action="store_true",
        help="disable checkpoint instrumentation for a controlled neutrality run",
    )
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
    if arguments.command == "compare-neutrality":
        neutrality_comparison = InstrumentationNeutralityComparison.compare(
            json.loads(arguments.instrumented.read_text()),
            json.loads(arguments.control.read_text()),
        )
        print(json.dumps(neutrality_comparison.to_dict(), indent=2, sort_keys=True))
        return 0 if neutrality_comparison.passed else 1

    profiles = {
        "scip-smoke": ScipSmokeProfile,
        "scip-highs-pricing": ScipHighsPricingProfile,
        "scip-highs-primal-basis": ScipHighsPrimalBasisProfile,
        "cplex-oracle": CplexOracleProfile,
    }
    profile = (
        ScipHighsPricingProfile(
            capture_state_evidence=not arguments.no_state_evidence
        )
        if arguments.profile == "scip-highs-pricing"
        else profiles[arguments.profile]()
    )
    baseline = (
        ObjectiveBaseline.load(arguments.baseline) if arguments.baseline else None
    )
    if (arguments.run_name is None) != (arguments.operation_mode is None):
        raise SystemExit("--run-name and --operation-mode must be supplied together")
    if arguments.run_name is None and (
        arguments.daily_mode is not None or arguments.case_id
    ):
        raise SystemExit(
            "--daily-mode/--case-id require --run-name and --operation-mode"
        )
    configuration = (
        VspdRunConfiguration(
            arguments.run_name,
            arguments.operation_mode,
            daily_mode=arguments.daily_mode,
            case_ids=tuple(arguments.case_id),
        )
        if arguments.run_name is not None and arguments.operation_mode is not None
        else None
    )
    result = VspdRunner().run(
        VspdCase(
            source_tree=arguments.source.resolve(),
            input_gdx=arguments.input.resolve(),
            work_directory=arguments.work_directory.resolve(),
            gams_executable=arguments.gams.resolve(),
            profile=profile,
            configuration=configuration,
        ),
        baseline=baseline,
        absolute_tolerance=arguments.absolute_tolerance,
        relative_tolerance=arguments.relative_tolerance,
    )
    payload = json.loads(result.evidence.read_text())
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not result.parsed.matches_profile(profile):
        return 1
    return 0 if result.qualified else 1


if __name__ == "__main__":
    raise SystemExit(main())
