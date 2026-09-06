"""Probity checks for the fresh current-code 2023-09-22 replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.evidence_support import require_external_evidence
from tools.gate12.energy_allocation import EnergyAllocationCertificateStore

_ROOT = Path(__file__).parents[2]
_EVIDENCE = _ROOT / "private/docs/gate-12"
_BENCHMARK = _EVIDENCE / "cplex-reference-paths-20230922-current-v3-full-day.json"
_RAW = _EVIDENCE / "cplex-reference-comparison-20230922-current-v3-full-day.json"
_CERTIFIED = (
    _EVIDENCE
    / "cplex-reference-comparison-20230922-current-v3-full-day-tp24-certified.json"
)
_CERTIFICATE = (
    _EVIDENCE / "cplex-tp24-energy-allocation-20230922-current-v3-full-day.json"
)


def _load(path: Path) -> dict:
    require_external_evidence(path, "gate12-solver-paths-v1")
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_full_day_is_complete_optimal_and_fail_closed() -> None:
    benchmark = _load(_BENCHMARK)
    run = benchmark["runs"][0]
    raw = _load(_RAW)["profiles"][0]
    certified = _load(_CERTIFIED)["profiles"][0]
    certificate = EnergyAllocationCertificateStore().load(_CERTIFICATE)

    assert run["completed"]
    assert run["case_count"] == 274
    assert run["solve_calls"] == 274
    assert run["case_retry_count"] == 0
    assert run["all_solves_optimal"]
    assert not run["independent_validation_passed"]
    assert run["maximum_validation_residual"] == 0.03336221585050225
    assert (
        run["records_sha256"]
        == "1778095deba472c22514ae751ca850a35b5d4c87b754bf5c53d765665998345b"
    )
    assert certificate.benchmark_sha256 == hashlib.sha256(
        _BENCHMARK.read_bytes()
    ).hexdigest()
    assert certificate.records_sha256 == run["records_sha256"]
    assert raw["compared_value_count"] == 3_964_727
    assert raw["above_precision_count"] == 28_472
    assert raw["certified_difference_count"] == 10_010
    assert certified["compared_value_count"] == raw["compared_value_count"]
    assert certified["certified_difference_count"] == (
        raw["certified_difference_count"] + 14
    )
    assert certified["above_precision_count"] == raw["above_precision_count"] - 14
    assert not certified["passed"]

    tables = {table["reference_table"]: table for table in certified["tables"]}
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 0
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 535
    assert tables["PublishedReservePrices_TP"]["above_precision_count"] == 2
