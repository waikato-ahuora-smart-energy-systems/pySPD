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
        "cplex-reference-comparison-20230922-tp13-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp14-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp15-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp16-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp19-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp20-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp21-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp24-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp25-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp26-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp30-passive-tree-six-cases.json",
        "cplex-reference-comparison-20230922-tp33-passive-tree-interval-certified.json",
    ),
)
def test_progressive_periods_pass_market_boundary(name: str) -> None:
    comparison = _load(name)["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 0
    assert tables["PublishedReservePrices_TP"]["above_precision_count"] == 0
    assert tables["SummaryResults_TP"]["above_precision_count"] == 0


def test_tp12_transit_interval_certifies_atu_publication() -> None:
    benchmark = _load(
        "cplex-reference-paths-20230922-tp12-transit-interval.json"
    )["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-tp12-transit-interval.json"
    )["profiles"][0]
    row = next(
        row
        for row in benchmark["published_price_rows"]
        if row["product"] == "energy"
        and row["trading_period"] == "TP12"
        and row["location"] == "ATU1101"
    )
    table = next(
        item
        for item in comparison["tables"]
        if item["reference_table"] == "PublishedEnergyPrices_TP"
    )

    assert benchmark["case_count"] == 6
    assert benchmark["all_solves_optimal"]
    assert benchmark["records_sha256"] == (
        "c5fd75d56bd00082b4438bc26103b068505f566ac2bd7a469d529f8e24642d74"
    )
    assert row["price_nzd_per_mwh"] == "99.951899999999995"
    assert row["price_interval"] == "[99.841729999999998,99.970020000000005]"
    assert table["above_precision_count"] == 0
    assert table["certified_difference_count"] == 2


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


def test_tp21_oro_publication_is_interval_certified() -> None:
    benchmark = _load(
        "cplex-reference-paths-20230922-tp21-passive-tree-six-cases.json"
    )["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-tp21-passive-tree-six-cases.json"
    )["profiles"][0]
    row = next(
        row
        for row in benchmark["published_price_rows"]
        if row["product"] == "energy"
        and row["trading_period"] == "TP21"
        and row["location"] == "ORO1101"
    )
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert benchmark["case_count"] == 6
    assert benchmark["all_solves_optimal"]
    assert row["price_nzd_per_mwh"] == "111.86839000000001"
    assert row["price_interval"] == "[111.86839000000001,113.03644]"
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 0
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 1


def test_tp21_cumulative_substitution_is_complete_and_hash_bound() -> None:
    payload = _load(
        "cplex-reference-paths-20230922-highs-passive-tree-tp21.json"
    )
    benchmark = payload["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-highs-passive-tree-tp21.json"
    )["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert benchmark["case_count"] == 274
    assert benchmark["solve_calls"] == 274
    assert benchmark["all_solves_optimal"]
    assert benchmark["records_sha256"] == (
        "44363979d693b51dd4d8dc32a6735e73d5c4dacf779bc4d824871c70b56bf0e9"
    )
    assert len(payload["record_substitution"]["case_ids"]) == 6
    assert comparison["above_precision_count"] == 30236
    assert comparison["certified_difference_count"] == 9907
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 187
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 523


def test_priority_period_cumulative_substitution_is_complete_and_hash_bound() -> None:
    payload = _load(
        "cplex-reference-paths-20230922-highs-passive-tree-priority.json"
    )
    benchmark = payload["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-highs-passive-tree-priority.json"
    )["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert benchmark["case_count"] == 274
    assert benchmark["solve_calls"] == 274
    assert benchmark["all_solves_optimal"]
    assert benchmark["records_sha256"] == (
        "cfa3f42af8c256714fb2714003cb2730ee063d5e9d0398dd6e4e2c1edfe51b18"
    )
    assert len(payload["record_substitution"]["replacement_summaries"]) == 4
    assert comparison["above_precision_count"] == 30155
    assert comparison["certified_difference_count"] == 9914
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 182
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 524


def test_complete_day_replay_is_optimal_complete_and_hash_bound() -> None:
    payload = _load(
        "cplex-reference-paths-20230922-highs-passive-tree-complete.json"
    )
    benchmark = payload["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-highs-passive-tree-complete.json"
    )["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert benchmark["case_count"] == 274
    assert benchmark["solve_calls"] == 274
    assert benchmark["case_retry_count"] == 0
    assert benchmark["all_solves_optimal"]
    assert benchmark["records_sha256"] == (
        "7d99a9bad276de152a1e7cc32c3d44913d93869435168ce092966b76160a8175"
    )
    assert comparison["missing_identity_count"] == 162
    assert comparison["extra_identity_count"] == 279
    assert comparison["above_precision_count"] == 29676
    assert comparison["certified_difference_count"] == 9999
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 170
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 533
    assert tables["PublishedReservePrices_TP"]["above_precision_count"] == 3
    assert tables["SummaryResults_TP"]["above_precision_count"] == 9


def test_root_boundary_cumulative_substitution_is_hash_bound() -> None:
    payload = _load(
        "cplex-reference-paths-20230922-highs-root-boundary-interval.json"
    )
    benchmark = payload["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-highs-root-boundary-interval.json"
    )["profiles"][0]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert benchmark["case_count"] == 274
    assert benchmark["solve_calls"] == 274
    assert benchmark["all_solves_optimal"]
    assert benchmark["records_sha256"] == (
        "919275b9f33262d2c766d1fd7fad855d0515d9438f88903b749f1ec0b0da9d02"
    )
    assert benchmark["replaced_case_count"] == 13
    assert comparison["above_precision_count"] == 29631
    assert comparison["certified_difference_count"] == 10044
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 167
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 536
    assert tables["PublishedReservePrices_TP"]["above_precision_count"] == 3
    assert tables["SummaryResults_TP"]["above_precision_count"] == 9


def test_tp1_parallel_root_interval_certifies_ari_publications() -> None:
    benchmark = _load(
        "cplex-reference-paths-20230922-tp1-root-boundary-interval.json"
    )["runs"][0]
    comparison = _load(
        "cplex-reference-comparison-20230922-tp1-root-boundary-interval.json"
    )["profiles"][0]
    rows = [
        row
        for row in benchmark["published_price_rows"]
        if row["product"] == "energy"
        and row["trading_period"] == "TP1"
        and row["location"] in {"ARI1101", "ARI1101 ARI0"}
    ]
    tables = {table["reference_table"]: table for table in comparison["tables"]}

    assert benchmark["case_count"] == 7
    assert benchmark["all_solves_optimal"]
    assert benchmark["records_sha256"] == (
        "8fc228482687073d2e757cd43dfbe34e8dcd90b341a3c6ac32d6bb07665ebc35"
    )
    assert len(rows) == 2
    assert {row["price_nzd_per_mwh"] for row in rows} == {
        "6.3969800000000001"
    }
    assert {row["price_interval"] for row in rows} == {
        "[6.3673400000000004,6.4173600000000004]"
    }
    assert tables["PublishedEnergyPrices_TP"]["above_precision_count"] == 0
    assert tables["PublishedEnergyPrices_TP"]["certified_difference_count"] == 363
    assert tables["PublishedReservePrices_TP"]["above_precision_count"] == 2


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
