"""Probity checks for the governed 2023-09-22 passive-tree correction."""

from __future__ import annotations

import json
from pathlib import Path

_EVIDENCE = Path(__file__).parents[2] / "docs/gate-12"


def _load(name: str) -> dict:
    return json.loads((_EVIDENCE / name).read_text(encoding="utf-8"))


def test_tp29_published_energy_and_summary_match_cplex_precision() -> None:
    comparison = _load(
        "cplex-reference-comparison-20230922-"
        "tp29-passive-tree-five-cases.json"
    )["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 0
    assert tables["SummaryResults_TP"]["above_precision_count"] == 0


def test_tp29_substitution_reconstructs_exact_oro_publication() -> None:
    benchmark = _load("cplex-reference-paths-20230922-highs-tp29-corrected.json")
    run = benchmark["runs"][0]

    assert run["completed"]
    assert run["all_solves_optimal"]
    assert run["case_count"] == 274
    assert run["solve_calls"] == 274
    assert run["replaced_case_count"] == 5
    oro = [
        row
        for row in run["published_price_rows"]
        if row["product"] == "energy"
        and row["trading_period"] == "TP29"
        and row["location"] == "ORO1101"
    ]
    assert len(oro) == 1
    assert oro[0]["price_nzd_per_mwh"] == "100.12922"


def test_tp29_substitution_exposes_next_unresolved_published_maximum() -> None:
    comparison = _load(
        "cplex-reference-comparison-20230922-highs-tp29-corrected.json"
    )["profiles"][0]
    table = next(
        item
        for item in comparison["tables"]
        if item["reference_table"] == "PublishedEnergyPrices_TP"
    )

    assert table["maximum_absolute_error"] == "0.382929999999995"
    assert table["maximum_difference"]["identity"] == [
        "22-SEP-2023 05:30",
        "TP12",
        "ORO1101",
        "published-energy-price",
    ]
