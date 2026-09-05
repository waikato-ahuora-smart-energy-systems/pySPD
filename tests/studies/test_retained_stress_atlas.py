from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from pyspd.studies import file_sha256

ROOT = Path(__file__).parents[2]
PREREGISTRATION = (
    ROOT / "docs/case-studies/evidence/historical-stress-event-atlas-v1/"
    "preregistration.json"
)
ATLAS = ROOT / "docs/case-studies/evidence/historical-stress-event-atlas-v1/atlas.json"


def test_retained_atlas_matches_the_preregistered_population() -> None:
    preregistration = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    events = atlas["events"]

    assert preregistration["status"] == "preregistered-before-classification"
    assert len(preregistration["source_manifests"]) == 3
    assert atlas["thresholds"] == preregistration["thresholds"]
    assert atlas["preregistration_sha256"] == file_sha256(PREREGISTRATION)
    assert len(events) == 21
    assert len({event["date"] for event in events}) == 21
    assert Counter(event["date"][:4] for event in events) == {
        "2019": 11,
        "2023": 10,
    }
    assert all(event["metrics"]["all_solves_successful"] for event in events)
    assert all(len(event["input_sha256"]) == 64 for event in events)
    assert all(len(event["result_tree_sha256"]) == 64 for event in events)
    logical_sha256 = atlas.pop("logical_sha256")
    encoded = json.dumps(atlas, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == logical_sha256


def test_retained_atlas_covers_registered_boundary_signals() -> None:
    events = json.loads(ATLAS.read_text(encoding="utf-8"))["events"]
    categories = Counter(
        category for event in events for category in event["categories"]
    )

    assert categories == {
        "dst-long-day": 1,
        "dst-short-day": 2,
        "high-energy-price": 1,
        "high-reserve-price": 2,
        "violation": 14,
    }
    by_date = {event["date"]: event for event in events}
    assert by_date["2019-04-07"]["metrics"]["period_count"] == 50
    assert by_date["2019-09-29"]["metrics"]["period_count"] == 46
    assert by_date["2023-09-24"]["metrics"]["period_count"] == 46
    assert by_date["2019-10-21"]["metrics"]["maximum_violation_mw"] == 11.8
    assert by_date["2023-08-02"]["metrics"]["maximum_reserve_price"] > 1_300
