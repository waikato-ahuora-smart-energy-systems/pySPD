"""Replay a GAMS Convert fixed-LP matrix through a GAMSPy solver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.oracle.gamspy_matrix import GamspyFixedMatrixOracle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--solver", default="CPLEX")
    parser.add_argument("--equation-contains", action="append", default=[])
    parser.add_argument(
        "--mip-then-fixed",
        action="store_true",
        help="solve exported discrete variables first, then price their fixed LP",
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = GamspyFixedMatrixOracle().solve(
        arguments.matrix,
        solver=arguments.solver,
        equation_contains=tuple(arguments.equation_contains),
        mip_then_fixed=arguments.mip_then_fixed,
        solver_options=(
            {
                "epopt": 1e-7,
                "eprhs": 1e-6,
                "numericalemphasis": 1,
                "scaind": 1,
            }
            if arguments.solver.casefold() == "cplex"
            else None
        ),
    )
    payload = json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
