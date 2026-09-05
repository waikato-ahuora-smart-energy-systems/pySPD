from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pyspd.studies.stress_atlas import (
    AtlasCorpusLoader,
    AtlasError,
    AtlasThresholds,
    HistoricalDaySource,
    StressCategory,
    StressEventAtlasBuilder,
    StressEventAtlasWriter,
    file_sha256,
    result_tree_sha256,
)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _source(tmp_path: Path) -> HistoricalDaySource:
    day_directory = tmp_path / "20240929"
    input_directory = day_directory / "input"
    input_directory.mkdir(parents=True)
    input_path = input_directory / "Pricing_20240929.gdx"
    input_path.write_bytes(b"hash-bound-gdx")
    results = day_directory / "results"
    results.mkdir()
    _write_csv(
        results / "day_SummaryResults_TP.csv",
        [
            "DateTime",
            "Period",
            "SolveStatus (1=OK)",
            "SystemCost",
            "ViolationCost",
            "DeficitGenViol (MW)",
        ],
        [
            ["29-SEP-2024 00:00", "TP1", 1, 100, 0, 0],
            ["29-SEP-2024 00:30", "TP2", 1, 200, 25, 0.5],
        ],
    )
    _write_csv(
        results / "day_node_results.csv",
        ["DateTime", "TP", "Node", "Price ($/MWh)"],
        [
            ["29-SEP-2024 00:00", "TP1", "N1", -2],
            ["29-SEP-2024 00:30", "TP2", "N1", 1500],
        ],
    )
    _write_csv(
        results / "day_reserve_results.csv",
        ["DateTime", "Island", "FIR Price ($/MW)", "SIR Price ($/MW)"],
        [["29-SEP-2024 00:30", "NI", 400, 10]],
    )
    _write_csv(
        results / "day_BranchResults_TP.csv",
        ["DateTime", "Branch", "Flow (MW) (From->To)", "Capacity (MW)"],
        [["29-SEP-2024 00:30", "B1", 99, 100]],
    )
    return HistoricalDaySource(
        date="2024-09-29",
        input_schema="vspd-v5.0.6",
        input_path=input_path,
        input_sha256=file_sha256(input_path),
        result_directory=results,
        result_tree_sha256=result_tree_sha256(results),
        source_profile="synthetic-reference-v1",
        selection_reason="predeclared edge fixture",
        expected_period_count=2,
    )


def test_builder_classifies_metrics_and_binds_all_sources(tmp_path: Path) -> None:
    source = _source(tmp_path)
    builder = StressEventAtlasBuilder(
        AtlasThresholds(
            high_energy_price=1000,
            negative_energy_price=0,
            high_reserve_price=300,
            network_utilization=0.98,
            violation_mw=1e-6,
        )
    )

    atlas = builder.build((source,), verify_hashes=True)
    event = atlas.events[0]

    assert event.date == "2024-09-29"
    assert event.input_path == "Pricing_20240929.gdx"
    assert event.metrics.period_count == 2
    assert event.metrics.summary_case_count == 2
    assert event.metrics.all_solves_successful is True
    assert event.metrics.total_system_cost == pytest.approx(300)
    assert event.metrics.total_violation_cost == pytest.approx(25)
    assert event.metrics.maximum_violation_mw == pytest.approx(0.5)
    assert event.metrics.minimum_energy_price == pytest.approx(-2)
    assert event.metrics.maximum_energy_price == pytest.approx(1500)
    assert event.metrics.maximum_reserve_price == pytest.approx(400)
    assert event.metrics.maximum_branch_utilization == pytest.approx(0.99)
    assert event.categories == (
        StressCategory.HIGH_ENERGY_PRICE,
        StressCategory.HIGH_RESERVE_PRICE,
        StressCategory.NEGATIVE_ENERGY_PRICE,
        StressCategory.NETWORK_STRESS,
        StressCategory.VIOLATION,
    )
    assert len(atlas.logical_sha256) == 64
    assert atlas.source_tree_sha256 != atlas.logical_sha256
    assert builder.build((source,), verify_hashes=True) == atlas


def test_hash_and_completeness_fail_closed(tmp_path: Path) -> None:
    source = _source(tmp_path)
    source.input_path.write_bytes(b"changed")
    with pytest.raises(AtlasError, match="input SHA-256"):
        StressEventAtlasBuilder().build((source,), verify_hashes=True)

    bad_count = HistoricalDaySource(
        date=source.date,
        input_schema=source.input_schema,
        input_path=source.input_path,
        input_sha256=file_sha256(source.input_path),
        result_directory=source.result_directory,
        result_tree_sha256=result_tree_sha256(source.result_directory),
        source_profile=source.source_profile,
        selection_reason=source.selection_reason,
        expected_period_count=48,
    )
    with pytest.raises(AtlasError, match="period count"):
        StressEventAtlasBuilder().build((bad_count,), verify_hashes=True)


def test_calendar_categories_and_deterministic_writer(tmp_path: Path) -> None:
    source = _source(tmp_path)
    source_50 = HistoricalDaySource(
        date="2024-04-07",
        input_schema=source.input_schema,
        input_path=source.input_path,
        input_sha256=source.input_sha256,
        result_directory=source.result_directory,
        result_tree_sha256=source.result_tree_sha256,
        source_profile=source.source_profile,
        selection_reason="fall-back",
        expected_period_count=2,
        declared_categories=(StressCategory.DST_LONG_DAY,),
    )
    atlas = StressEventAtlasBuilder().build((source_50,), verify_hashes=True)
    assert StressCategory.DST_LONG_DAY in atlas.events[0].categories

    output = tmp_path / "atlas"
    files = StressEventAtlasWriter().write(atlas, output)
    assert tuple(path.name for path in files) == (
        "atlas.json",
        "events.csv",
        "README.md",
    )
    payload = json.loads((output / "atlas.json").read_text(encoding="utf-8"))
    assert payload["logical_sha256"] == atlas.logical_sha256
    assert "Historical stress-event atlas" in (output / "README.md").read_text()


def test_manifest_loader_deduplicates_and_rejects_conflicts(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manifest = tmp_path / "manifest.json"
    day = {
        "year": 2024,
        "date": source.date,
        "input_schema": source.input_schema,
        "input": str(source.input_path.relative_to(tmp_path)),
        "input_sha256": source.input_sha256,
        "result_tree_sha256": source.result_tree_sha256,
        "summary_rows": 2,
        "selection_reason": source.selection_reason,
    }
    manifest.write_text(
        json.dumps({"profile": source.source_profile, "days": [day]}),
        encoding="utf-8",
    )
    loaded = AtlasCorpusLoader().load((manifest, manifest))
    assert len(loaded) == 1
    assert loaded[0].result_directory == source.result_directory

    conflicting = dict(day, input_sha256="0" * 64)
    manifest.write_text(
        json.dumps({"profile": source.source_profile, "days": [day, conflicting]}),
        encoding="utf-8",
    )
    with pytest.raises(AtlasError, match="conflicting duplicate"):
        AtlasCorpusLoader().load((manifest,))
