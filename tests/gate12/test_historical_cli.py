"""Tests for the Gate 12 historical enumeration command contract."""

from __future__ import annotations

import pytest

from tools.gate12.enumerate_historical import build_parser


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
