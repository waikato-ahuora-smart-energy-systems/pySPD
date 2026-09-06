"""Probity contracts for the Stage 13 paper-replication entry boundary."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_stage13_source_register_fails_closed_before_full_text_acquisition() -> None:
    register = json.loads(
        (ROOT / "private/docs/gate-13/paper-source-register.json").read_text()
    )

    assert register["article"]["doi"] == "10.1016/j.energy.2026.141862"
    assert register["article"]["pii"] == "S0360544226019699"
    assert register["full_text"] == {
        "acquired": False,
        "file_sha256": None,
        "notes": (
            "Publisher page was access-restricted; no full-text method or result "
            "claim is admitted from abstract metadata."
        ),
        "supplements_acquired": False,
    }
    assert not register["method_boundary"]["full_method_extracted"]
    assert not register["method_boundary"]["replication_implementation_authorized"]


def test_stage13_plan_requires_modular_overlay_and_honest_claims() -> None:
    plan = (ROOT / "private/docs/pyomo-vspd-stage-gate-plan.md").read_text()

    for required in (
        "### Stage 13 — Residential-PV counterfactual study replication",
        "ResidentialPvScenarioDefinition",
        "ResidentialPvNodeAllocator",
        "ResidentialPvTemporalMapper",
        "ResidentialPvLoadOverlay",
        "ResidentialPvExperimentRunner",
        "ResidentialPvReplicationComparator",
        "#### Gate 13 — Residential-PV study replicated",
        "REPLICATED",
        "PARTIALLY REPLICATED",
        "NOT REPRODUCIBLE",
    ):
        assert required in plan

    assert "must not silently change the v5 or v16 compatibility models" in plan
    assert "Probity TDD applies to every Stage 13 production change" in plan
