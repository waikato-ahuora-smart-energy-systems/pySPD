"""Probity checks for the governed 2023-09-22 passive-tree correction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    "name",
    (
        "cplex-reference-comparison-20230922-tp10-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp14-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp15-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp16-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp19-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp20-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp25-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp33-passive-tree-interval-certified.json",
    ),
)
def test_progressive_periods_pass_market_boundary(name: str) -> None:
    comparison = _load(name)["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 0
    assert tables["PublishedReservePrices_TP"]["above_precision_count"] == 0
    assert tables["SummaryResults_TP"]["above_precision_count"] == 0


def test_tp12_retains_only_unrelated_atu_publication_residual() -> None:
    comparison = _load(
        "cplex-reference-comparison-20230922-"
        "tp12-passive-tree-interval-certified.json"
    )["profiles"][0]
    table = next(
        item
        for item in comparison["tables"]
        if item["reference_table"] == "PublishedEnergyPrices_TP"
    )

    assert table["above_precision_count"] == 1
    assert table["certified_difference_count"] == 1


def test_tp33_published_interval_contains_cplex_price() -> None:
    benchmark = _load(
        "cplex-reference-paths-20230922-"
        "tp33-passive-tree-interval-certified.json"
    )["runs"][0]
    row = next(
        row
        for row in benchmark["published_price_rows"]
        if row["product"] == "energy"
        and row["trading_period"] == "TP33"
        and row["location"] == "ORO1101"
    )

    assert row["price_nzd_per_mwh"] == "147.31281000000001"
    assert row["price_interval"] == "[147.31281000000001,148.5197]"


def test_partial_day_evidence_is_complete_and_hash_bound() -> None:
    payload = _load(
        "cplex-reference-paths-20230922-highs-passive-tree-partial.json"
    )
    benchmark = payload["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-highs-passive-tree-partial.json"
    )["profiles"][0]

    assert benchmark["case_count"] == 274
    assert benchmark["solve_calls"] == 274
    assert benchmark["all_solves_optimal"]
    assert benchmark["replaced_case_count"] == 59
    assert benchmark["records_sha256"] == (
        "891c184f2cd3e45d76da4f6ab88669130d0de6b85bac388dee863bf98670bad4"
    )
    assert comparison["above_precision_count"] == 34237
    assert len(payload["record_substitution"]["replacement_summaries"]) == 10
    tables = {table["reference_table"]: table for table in comparison["tables"]}
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 188
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 522
