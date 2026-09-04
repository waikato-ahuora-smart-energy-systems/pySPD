"""Probity checks for the fail-closed 2023-09-22 TP1 reserve residue."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_EVIDENCE = _ROOT / "docs/gate-12/cplex-tp1-reserve-residue-20230922.json"
_INPUT = (
    _ROOT
    / "tests/fixtures/cplex_reference/2023/20230922/input/Pricing_20230922.gdx"
)
_RESULTS = _ROOT / "tests/fixtures/cplex_reference/2023/20230922/results"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_tp1_reserve_residue_is_hash_bound_and_fails_closed() -> None:
    evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    logical_sha256 = evidence.pop("logical_sha256")

    assert logical_sha256 == hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert evidence["profile"] == "cplex-tp1-reserve-residue-v1"
    assert evidence["conclusion"]["accepted"] is False
    assert not evidence["diagnostics"]["two_sided_finite_difference"][
        "archive_inside_current_scalar_interval"
    ]
    assert not evidence["diagnostics"]["reserve_zone_enumeration"][
        "archive_reproduced"
    ]
    assert evidence["source"] == {
        "input_sha256": _sha256(_INPUT),
        "island_results_sha256": _sha256(
            _RESULTS / "2023-09-22_base_vSPD_raw_IslandResults_TP.csv"
        ),
        "summary_results_sha256": _sha256(
            _RESULTS / "2023-09-22_base_vSPD_raw_SummaryResults_TP.csv"
        ),
    }

    for case in evidence["cases"]:
        assert case["archive"]["si_fir_nzd_per_mwh"] != case[
            "current_fixed_rmip"
        ]["si_fir_nzd_per_mwh"]
        assert case["forced_archive_flow"]["si_fir_nzd_per_mwh"] == 0.01
        assert case["forced_archive_flow"]["objective_delta_nzd"] < 0.0
