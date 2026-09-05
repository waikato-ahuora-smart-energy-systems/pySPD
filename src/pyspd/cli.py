"""Stable command line interface for PySPD."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from pyspd.application import (
    ApplicationConfiguration,
    ConfigurationError,
    PyspdApplication,
)


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="pyspd")
    commands = root.add_subparsers(dest="command", required=True)
    formulations = commands.add_parser("formulations")
    formulations.add_argument("--json", action="store_true", dest="as_json")
    run = commands.add_parser("run")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument(
        "--workers",
        type=_positive_integer,
        help="override the configured number of independent case workers",
    )
    return root


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    application = PyspdApplication()
    if arguments.command == "formulations":
        payload = {"formulations": list(application.formulation_ids)}
        if arguments.as_json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print("\n".join(payload["formulations"]))
        return 0
    try:
        configuration = ApplicationConfiguration.from_json(arguments.config)
        if arguments.workers is not None:
            configuration = replace(configuration, worker_count=arguments.workers)
        run = application.run(configuration)
    except (ConfigurationError, OSError, ValueError) as error:
        print(f"pyspd: {error}")
        return 2
    print(
        json.dumps(
            {
                "output_directory": str(run.output_directory),
                "report_manifest_sha256": run.report_manifest.logical_sha256,
                "state": run.result.state.value,
            },
            sort_keys=True,
        )
    )
    return 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
