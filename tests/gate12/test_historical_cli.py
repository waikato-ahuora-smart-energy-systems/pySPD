"""Tests for the Gate 12 historical enumeration command contract."""

from __future__ import annotations

import pytest

from tools.gate12.enumerate_historical import HistoricalEnumerationOutcome, build_parser


def test_historical_cli_requires_all_reproducibility_inputs() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--source-tree",
            "/source",
            "--work-directory",
            "/work",
            "--input-root",
            "/inputs",
            "--inventory",
            "/inventory.json",
            "--gams-executable",
            "/gams/gams",
            "--system-directory",
            "/gams",
        ]
    )

    assert str(arguments.inventory) == "/inventory.json"
    assert str(arguments.work_directory) == "/work"
    assert arguments.execution_scope == "population"
    assert arguments.network_license_attempts == 6
    assert arguments.network_license_retry_seconds == 300.0


def test_historical_cli_has_explicit_non_qualifying_shard_scope() -> None:
    parser = build_parser()

    arguments = parser.parse_args(
        [
            "--source-tree",
            "/source",
            "--work-directory",
            "/work",
            "--input-root",
            "/inputs",
            "--inventory",
            "/inventory.json",
            "--gams-executable",
            "/gams/gams",
            "--system-directory",
            "/gams",
            "--execution-scope",
            "shard",
        ]
    )

    assert arguments.execution_scope == "shard"


def test_complete_shard_succeeds_without_claiming_population_parity() -> None:
    outcome = HistoricalEnumerationOutcome.evaluate(
        execution_scope="shard",
        inventory_count=35,
        checkpoint_count=35,
        affected_interval_count=120,
    )

    assert outcome.execution_passed
    assert outcome.shard_complete
    assert not outcome.population_passed
    assert not outcome.emit_manifest


def test_population_scope_remains_fail_closed_at_wrong_declared_count() -> None:
    outcome = HistoricalEnumerationOutcome.evaluate(
        execution_scope="population",
        inventory_count=139,
        checkpoint_count=139,
        affected_interval_count=545,
    )

    assert not outcome.execution_passed
    assert outcome.shard_complete
    assert not outcome.population_passed
    assert not outcome.emit_manifest
