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
from pyspd.evidence import (
    EvidenceError,
    EvidenceManifest,
    EvidenceStore,
    default_evidence_cache,
    github_credential,
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
    evidence = commands.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(
        dest="evidence_command", required=True
    )
    for name in ("list", "fetch", "verify"):
        command = evidence_commands.add_parser(name)
        command.add_argument(
            "--manifest",
            type=Path,
            default=Path("evidence/manifest-v1.json"),
        )
        if name != "list":
            command.add_argument("artifact_id")
            command.add_argument(
                "--cache", type=Path, default=default_evidence_cache()
            )
            command.add_argument(
                "--github-auth",
                action="store_true",
                help="authenticate downloads with the configured GitHub credential",
            )
        if name == "fetch":
            command.add_argument("--destination", type=Path, default=Path.cwd())
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
    if arguments.command == "evidence":
        try:
            manifest = EvidenceManifest.from_json(arguments.manifest)
            if arguments.evidence_command == "list":
                print(
                    json.dumps(
                        {
                            "logical_sha256": manifest.logical_sha256,
                            "artifacts": [
                                artifact.to_dict() for artifact in manifest.artifacts
                            ],
                        },
                        sort_keys=True,
                    )
                )
                return 0
            artifact = manifest.artifact(arguments.artifact_id)
            store = EvidenceStore(
                arguments.cache,
                auth_token=(github_credential() if arguments.github_auth else None),
            )
            if arguments.evidence_command == "verify":
                archive = store.verify(artifact)
                print(
                    json.dumps(
                        {
                            "artifact_id": artifact.artifact_id,
                            "archive_path": str(archive),
                            "verified": True,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            result = store.fetch(artifact, destination=arguments.destination)
            print(
                json.dumps(
                    {
                        "artifact_id": artifact.artifact_id,
                        "archive_path": str(result.archive_path),
                        "destination": str(result.destination),
                        "downloaded": result.downloaded,
                        "extracted_file_count": len(result.extracted_files),
                        "verified": result.verified,
                    },
                    sort_keys=True,
                )
            )
            return 0
        except (EvidenceError, OSError) as error:
            print(f"pyspd: {error}")
            return 2
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
