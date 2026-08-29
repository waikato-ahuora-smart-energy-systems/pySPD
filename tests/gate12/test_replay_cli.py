"""Command contract for materializing prefix-complete Gate 12 replays."""

from __future__ import annotations

import pytest

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import (
    HistoricalInputArtifact,
    HistoricalInputInventory,
)
from tools.gate12.plan_affected_replays import HistoricalReplayPlanWriter, build_parser


def test_replay_plan_cli_requires_all_provenance_inputs() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--manifest",
            "/manifest.json",
            "--inventory",
            "/inventory.json",
            "--input-root",
            "/inputs",
            "--system-directory",
            "/gams",
            "--output-directory",
            "/output",
        ]
    )

    assert str(arguments.manifest) == "/manifest.json"
    assert str(arguments.output_directory) == "/output"


def test_replay_plan_writer_is_atomic_and_hashes_each_configuration(tmp_path) -> None:
    output = tmp_path / "replays"
    inventory = HistoricalInputInventory(
        (HistoricalInputArtifact("20221106", 1, "1" * 64),)
    )
    plan = {
        "logical_sha256": "2" * 64,
        "batches": [
            {
                "trading_date": "20221106",
                "case_ids": ["warmup", "affected"],
            }
        ],
    }
    writer = HistoricalReplayPlanWriter()

    writer.write(
        plan_payload=plan,
        inventory=inventory,
        input_root=tmp_path / "inputs",
        system_directory=tmp_path / "gams",
        output_directory=output,
        manifest_sha256="3" * 64,
        inventory_sha256="4" * 64,
    )

    assert (output / "replay-plan.json").is_file()
    index = (output / "replay-index.json").read_text(encoding="utf-8")
    assert "configuration_sha256" in index
    config = (output / "configs" / "20221106.json").read_text(encoding="utf-8")
    assert "scip-mip-fixed-highs-rmip" in config
    assert '"warmup"' in config
    with pytest.raises(EvidenceContractError, match="already exists"):
        writer.write(
            plan_payload=plan,
            inventory=inventory,
            input_root=tmp_path / "inputs",
            system_directory=tmp_path / "gams",
            output_directory=output,
            manifest_sha256="3" * 64,
            inventory_sha256="4" * 64,
        )
