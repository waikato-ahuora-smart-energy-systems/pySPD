"""Command contract for incremental PySPD replay production."""

from __future__ import annotations

import pytest

from tools.gate12.compare_incremental_replays import (
    build_parser as compare_parser,
)
from tools.gate12.materialize_incremental_gams import (
    build_parser as gams_parser,
)
from tools.gate12.materialize_incremental_pyspd import build_parser


def test_incremental_pyspd_cli_requires_provenance_and_output_roots() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--discovery-checkpoints",
            "/discovery",
            "--inventory",
            "/inventory.json",
            "--input-root",
            "/inputs",
            "--system-directory",
            "/gams",
            "--bundle-root",
            "/bundles",
            "--run-root",
            "/runs",
            "--watch",
            "--maximum-new-dates",
            "1",
        ]
    )

    assert str(arguments.discovery_checkpoints) == "/discovery"
    assert str(arguments.bundle_root) == "/bundles"
    assert arguments.watch
    assert arguments.poll_seconds == 60.0
    assert arguments.maximum_new_dates == 1


def test_incremental_compare_cli_requires_both_bundle_roots() -> None:
    parser = compare_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--discovery-checkpoints",
            "/discovery",
            "--inventory",
            "/inventory.json",
            "--input-root",
            "/inputs",
            "--system-directory",
            "/gams",
            "--reference-bundle-root",
            "/reference",
            "--candidate-bundle-root",
            "/candidate",
            "--parity-checkpoints",
            "/parity",
        ]
    )

    assert str(arguments.reference_bundle_root) == "/reference"
    assert str(arguments.candidate_bundle_root) == "/candidate"
    assert str(arguments.parity_checkpoints) == "/parity"


def test_incremental_gams_cli_requires_pinned_source_and_executable() -> None:
    parser = gams_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--discovery-checkpoints",
            "/discovery",
            "--inventory",
            "/inventory.json",
            "--input-root",
            "/inputs",
            "--system-directory",
            "/gams",
            "--source-tree",
            "/pinned-vspd",
            "--gams-executable",
            "/gams/gams",
            "--bundle-root",
            "/reference",
            "--run-root",
            "/runs",
        ]
    )

    assert str(arguments.source_tree) == "/pinned-vspd"
    assert str(arguments.gams_executable) == "/gams/gams"
    assert str(arguments.bundle_root) == "/reference"
