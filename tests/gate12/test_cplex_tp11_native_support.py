"""Probity contract for the 2023-09-22 TP11 native-SOS correction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.evidence_support import require_external_evidence

_ROOT = Path(__file__).parents[2]
_MANIFEST = (
    _ROOT
    / "docs/gate-12/cplex-reference-paths-20230922-tp11-native-1e7.json"
)
_INPUT = (
    _ROOT
    / "tests/fixtures/cplex_reference/2023/20230922/input/Pricing_20230922.gdx"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_tp11_native_support_prefix_is_hash_bound_and_validated() -> None:
    require_external_evidence(_MANIFEST, "gate12-solver-paths-v1")
    require_external_evidence(_INPUT, "cplex-reference-v1")
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    logical_sha256 = manifest.pop("logical_sha256")

    assert logical_sha256 == hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert manifest["source_sha256"] == _sha256(_INPUT)
    run = manifest["runs"][0]
    assert run["completed"]
    assert run["case_count"] == 47
    assert run["case_retry_count"] == 0
    assert run["all_solves_optimal"]
    assert run["independent_validation_passed"]
    assert run["maximum_validation_residual"] <= 1.5e-5
    assert run["records_sha256"] == (
        "eae4acd11331b1e24858b8d2679d9bda94b5bb6b602f07f9fae3fffc6bcade9c"
    )


def test_tp11_prefix_publishes_cplex_ni_sir_price() -> None:
    require_external_evidence(_MANIFEST, "gate12-solver-paths-v1")
    run = json.loads(_MANIFEST.read_text(encoding="utf-8"))["runs"][0]
    rows = [
        row
        for row in run["published_price_rows"]
        if row["trading_period"] == "TP11"
        and row["location"] == "NI"
        and row["product"] == "SIR"
    ]

    assert len(rows) == 1
    assert float(rows[0]["price_nzd_per_mwh"]) == pytest.approx(0.10350)
