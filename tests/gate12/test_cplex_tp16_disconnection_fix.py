"""Probity checks for the governed 2023-11-24 TP16 correction evidence."""

from __future__ import annotations

import json
from pathlib import Path

from tests.evidence_support import require_external_evidence

_EVIDENCE = Path(__file__).parents[2] / "docs/gate-12"


def _load(name: str) -> dict:
    path = _EVIDENCE / name
    if name.startswith("cplex-reference-paths-"):
        require_external_evidence(path, "gate12-solver-paths-v1")
    return json.loads(path.read_text(encoding="utf-8"))


def test_tp16_targeted_rows_match_cplex_at_report_precision() -> None:
    comparison = _load(
        "cplex-reference-comparison-20231124-"
        "tp16-source-disconnection-three-cases.json"
    )["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    for name in (
        "BidResults_TP",
        "BrConstraintResults_TP",
        "BranchResults_TP",
        "BusResults_TP",
        "IslandResults_TP",
        "OfferResults_TP",
        "ReserveResults_TP",
        "RiskResults_TP",
        "SummaryResults_TP",
    ):
        assert tables[name]["above_precision_count"] == 0


def test_corrected_full_day_is_complete_and_publishes_exact_aby_tp16() -> None:
    benchmark = _load("cplex-reference-paths-20231124-highs-corrected.json")
    run = benchmark["runs"][0]

    assert run["completed"]
    assert run["all_solves_optimal"]
    assert run["case_count"] == 297
    assert run["solve_calls"] == 297
    assert run["replaced_case_count"] == 3
    aby = [
        row
        for row in run["published_price_rows"]
        if row["product"] == "energy"
        and row["trading_period"] == "TP16"
        and row["location"] == "ABY0111"
    ]
    assert len(aby) == 1
    assert aby[0]["price_nzd_per_mwh"] == "158.78761"


def test_corrected_full_day_worst_published_energy_delta_is_tp29_basis_case() -> None:
    comparison = _load(
        "cplex-reference-comparison-20231124-highs-corrected.json"
    )["profiles"][0]
    table = next(
        item
        for item in comparison["tables"]
        if item["reference_table"] == "PublishedEnergyPrices_TP"
    )

    assert table["maximum_absolute_error"] == "2.51038999999999"
    assert table["maximum_difference"]["identity"] == [
        "24-NOV-2023 14:00",
        "TP29",
        "ARG1101",
        "published-energy-price",
    ]
