"""Command contract for incremental PySPD replay production."""

from __future__ import annotations

import pytest

from tools.gate12.certify_bus_price_degeneracy import (
    build_parser as bus_certificate_parser,
)
from tools.gate12.compare_incremental_replays import (
    build_parser as compare_parser,
)
from tools.gate12.materialize_incremental_gams import (
    build_parser as gams_parser,
)
from tools.gate12.materialize_incremental_pyspd import build_parser
from tools.gate12.quantify_canonical_replay import (
    build_parser as quantify_parser,
)
from tools.gate12.validate_semantic_replay import (
    build_parser as semantic_parser,
)


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


def test_quantified_diff_cli_requires_a_paired_date_and_output() -> None:
    parser = quantify_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--reference-bundle-root",
            "/reference",
            "--candidate-bundle-root",
            "/candidate",
            "--trading-date",
            "20221106",
            "--output",
            "/diffs/20221106.json",
        ]
    )

    assert arguments.trading_date == "20221106"
    assert str(arguments.output) == "/diffs/20221106.json"


def test_semantic_validator_cli_requires_a_paired_date_and_output() -> None:
    parser = semantic_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--reference-bundle-root",
            "/reference",
            "--candidate-bundle-root",
            "/candidate",
            "--trading-date",
            "20221106",
            "--output",
            "/semantic/20221106.json",
            "--bus-price-certificate",
            "/certificates/20221106.json",
        ]
    )

    assert arguments.trading_date == "20221106"
    assert str(arguments.output) == "/semantic/20221106.json"
    assert str(arguments.bus_price_certificate) == "/certificates/20221106.json"


def test_bus_degeneracy_cli_requires_source_matrix_and_paired_bundles() -> None:
    parser = bus_certificate_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    arguments = parser.parse_args(
        [
            "--input",
            "/inputs/Pricing_20221106.gdx",
            "--system-directory",
            "/gams",
            "--reference-bundle-root",
            "/reference",
            "--candidate-bundle-root",
            "/candidate",
            "--trading-date",
            "20221106",
            "--output",
            "/certificates/20221106.json",
        ]
    )

    assert str(arguments.input) == "/inputs/Pricing_20221106.gdx"
    assert arguments.trading_date == "20221106"
