from __future__ import annotations

from collections import defaultdict

import pytest

from tools.merge_solver_path_shards import _accumulate_published, _validate


def test_shard_publication_accumulator_preserves_authoritative_weights() -> None:
    energy: dict[tuple[str, str], float] = defaultdict(float)
    reserve: dict[tuple[str, str, str], float] = defaultdict(float)
    seconds: dict[str, float] = defaultdict(float)
    date_time: dict[str, str] = {}
    record = {
        "trading_period": "TP1",
        "publication_seconds": 300.0.hex(),
        "date_time": "01-JAN-2024 00:00",
        "prices": {
            "node": [[["C1", "D1", "N1"], 20.0.hex()]],
            "reserve": [[["C1", "D1", "NI", "FIR"], 2.0.hex()]],
        },
    }

    _accumulate_published(record, energy, reserve, seconds, date_time)

    assert energy == {("TP1", "N1"): 6000.0}
    assert reserve == {("TP1", "NI", "FIR"): 600.0}
    assert seconds == {"TP1": 300.0}
    assert date_time == {"TP1": "01-JAN-2024 00:00"}


def test_shard_merge_rejects_provenance_or_profile_mismatch() -> None:
    base = {
        "schema_version": 5,
        "source_name": "Pricing.gdx",
        "source_sha256": "0" * 64,
        "input_schema": "vspd-v5.0.6",
        "environment": "Darwin-arm64",
        "validation_tolerance": 1e-4,
        "runs": [{"profile": "scip-mip-fixed-highs-rmip", "completed": True}],
    }
    different = {
        **base,
        "source_sha256": "1" * 64,
        "runs": [{"profile": "scip-mip-fixed-highs-rmip", "completed": True}],
    }

    with pytest.raises(ValueError, match="provenance"):
        _validate([base, different], [base["runs"][0], different["runs"][0]])

    different_schema = {**base, "schema_version": 4}
    with pytest.raises(ValueError, match="provenance"):
        _validate(
            [base, different_schema],
            [base["runs"][0], different_schema["runs"][0]],
        )
