from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def test_incremental_projection_manifest_is_complete_and_unambiguous() -> None:
    path = (
        Path(__file__).parents[2]
        / "docs"
        / "gate-1"
        / "incremental-matrix-mappings.json"
    )
    payload: dict[str, Any] = json.loads(path.read_text())
    stages = payload["stages"]
    equations = [
        family
        for stage in stages.values()
        for family in stage["equation_families"]
    ]
    variables = [
        family
        for stage in stages.values()
        for family in stage["variable_families"]
    ]

    assert payload["schema_version"] == 1
    assert list(stages) == ["4", "5", "6", "7"]
    assert len(equations) == len(set(equations)) == 77
    assert len(variables) == len(set(variables)) == 64
    assert payload["excluded_dictionary_families"]["equations"] == [
        "ObjectiveFunction"
    ]
    assert payload["nonidentity_transforms"] == []
    assert set(payload["transform_contracts"]) == {
        "row_sign",
        "ranged_row_split",
        "auxiliary_elimination",
    }
