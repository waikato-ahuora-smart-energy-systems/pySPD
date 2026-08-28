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


def test_gate1_shortfall_qualification_retains_gate8_obligation() -> None:
    root = Path(__file__).parents[2]
    gate = root / "docs" / "gate-1"
    inventory: dict[str, Any] = json.loads(
        (gate / "shortfall-input-inventory.json").read_text()
    )
    population: dict[str, Any] = json.loads(
        (gate / "shortfall-transfer-population.json").read_text()
    )
    characterization: dict[str, Any] = json.loads(
        (gate / "shortfall-characterization.json").read_text()
    )
    daylight: dict[str, Any] = json.loads(
        (gate / "daylight-saving-characterization.json").read_text()
    )

    assert inventory["declared_affected_interval_count"] == 546
    assert inventory["artifact_count"] == 139
    assert len(inventory["artifacts"]) == 139
    assert len({item["trading_date"] for item in inventory["artifacts"]}) == 139
    assert population["gate_1_qualification_adr"] == "ADR-0010"
    assert "all 546" in population["gate_8_obligation"]
    assert characterization["gate_policy_decision"]["gate_1_status"] == "qualified"
    assert characterization["gate_policy_decision"]["relaxed_selector_prohibited"]
    assert daylight["status"] == "qualified"
    assert {item["local_trading_period_count"] for item in daylight["fixtures"]} == {
        46,
        50,
    }
    assert all(item["all_solves_optimal"] for item in daylight["fixtures"])
