"""Probity checks for consecutive-day CPLEX confidence evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]
_EVIDENCE = _ROOT / "docs/gate-12"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    (
        "date",
        "case_count",
        "maximum_residual",
        "records_sha256",
        "certified_counts",
    ),
    (
        (
            "20230923",
            275,
            4.8e-7,
            "f8908981c2ad6a6cafb4ed884712c194665150430e23841f1b0c5eb8385d1a5b",
            (622, 3, 3),
        ),
        (
            "20230924",
            254,
            1.2e-7,
            "efe96f61325781e87f3e5b6e9f88c99107467e999e33fc6b697a748e979c1e13",
            (323, 7, 7),
        ),
        (
            "20230925",
            292,
            1.3e-5,
            "f05672e032abecc2b07b169853e8930e6d44d5220b59eaa8d1def433cc91ae2b",
            (310, 1, 0),
        ),
        (
            "20230926",
            295,
            2.4e-11,
            "90c9cbf039bf685260690e495594ba1e1cc0c77d0164a6018a5af1df103cb2ad",
            (83, 0, 0),
        ),
        (
            "20230927",
            263,
            1.8e-8,
            "ab21f4072cc4d92c945302ee510fac46e97e31a73e01c1a56c239b566fc7f474",
            (112, 0, 0),
        ),
    ),
)
def test_consecutive_day_market_result_boundary_is_clean_and_hash_bound(
    date: str,
    case_count: int,
    maximum_residual: float,
    records_sha256: str,
    certified_counts: tuple[int, int, int],
) -> None:
    evidence_variant = "full-day" if date == "20230926" else "certified"
    benchmark_path = (
        _EVIDENCE / f"cplex-reference-paths-{date}-{evidence_variant}.json"
    )
    comparison_path = (
        _EVIDENCE / f"cplex-reference-comparison-{date}-{evidence_variant}.json"
    )
    benchmark = _load(benchmark_path)
    run = benchmark["runs"][0]
    comparison = _load(comparison_path)
    profile = comparison["profiles"][0]
    tables = {table["reference_table"]: table for table in profile["tables"]}

    assert comparison["benchmark_sha256"] == hashlib.sha256(
        benchmark_path.read_bytes()
    ).hexdigest()
    assert run["completed"]
    assert run["case_count"] == case_count
    assert run["solve_calls"] == case_count
    assert run["all_solves_optimal"]
    assert run["independent_validation_passed"]
    assert run["maximum_validation_residual"] <= maximum_residual
    assert run["records_sha256"] == records_sha256
    for table_name in (
        "PublishedEnergyPrices_TP",
        "PublishedReservePrices_TP",
        "ReserveResults_TP",
    ):
        assert tables[table_name]["above_precision_count"] == 0
    assert tuple(
        tables[table_name]["certified_difference_count"]
        for table_name in (
            "PublishedEnergyPrices_TP",
            "PublishedReservePrices_TP",
            "ReserveResults_TP",
        )
    ) == certified_counts


@pytest.mark.parametrize(
    ("date", "expected_periods"),
    (
        ("20230923", 48),
        ("20230924", 46),
        ("20230925", 48),
        ("20230926", 48),
        ("20230927", 48),
    ),
)
def test_cplex_and_pyspd_share_the_dst_aware_trading_period_axis(
    date: str,
    expected_periods: int,
) -> None:
    evidence_variant = "full-day" if date == "20230926" else "certified"
    benchmark_path = (
        _EVIDENCE / f"cplex-reference-paths-{date}-{evidence_variant}.json"
    )
    benchmark = _load(benchmark_path)
    run = benchmark["runs"][0]
    records_path = _ROOT / run["records_path"]
    records = tuple(
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
    )
    seconds_by_period: dict[str, float] = defaultdict(float)
    for record in records:
        seconds_by_period[record["trading_period"]] += float.fromhex(
            record["publication_seconds"]
        )

    candidate_axis = {
        (row["trading_period"], row["date_time"])
        for row in run["published_price_rows"]
        if row["product"] == "energy"
    }
    results = (
        _ROOT
        / "tests/fixtures/cplex_consecutive/2023"
        / date
        / "results"
    )
    reference_path = next(results.glob("*raw_PublishedEnergyPrices_TP.csv"))
    with reference_path.open(newline="", encoding="utf-8-sig") as handle:
        reference_axis = {
            (row["TradingPeriod"], row["DateTime"])
            for row in csv.DictReader(handle)
        }

    assert candidate_axis == reference_axis
    assert len(candidate_axis) == expected_periods
    assert len(seconds_by_period) == expected_periods
    assert set(seconds_by_period.values()) == {1800.0}
    if date == "20230924":
        axis = dict(candidate_axis)
        assert axis["TP4"] == "24-SEP-2023 01:30"
        assert axis["TP5"] == "24-SEP-2023 03:00"
        assert axis["TP46"] == "24-SEP-2023 23:30"
        assert not any(" 02:" in date_time for date_time in axis.values())
