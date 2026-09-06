"""Probity checks for the governed TP29 CPLEX basis diagnosis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_tp29_diagnosis_is_objective_and_state_exact() -> None:
    path = (
        Path(__file__).parents[2]
        / "private/docs/gate-12/cplex-tp29-mip-basis-diagnosis-20231124.json"
    )
    evidence = json.loads(path.read_text(encoding="utf-8"))
    candidate = evidence["scip_mip_highs_fixed_rmip"]
    fixed = evidence["gamspy_cplex_replays"][
        "fresh_cplex_on_scip_fixed_matrix"
    ]
    continued = evidence["gamspy_cplex_replays"][
        "cplex_mip_then_fixed_cplex_rmip"
    ]

    assert candidate["system_objective"] == fixed["system_objective"]
    assert fixed["system_objective"] == continued["pricing_objective"]
    assert fixed["case_node_price_nzd_per_mwh"] == pytest.approx(
        candidate["case_node_price_nzd_per_mwh"], abs=2e-11
    )
    assert continued["case_node_price_nzd_per_mwh"] == pytest.approx(
        evidence["archive"]["case_bus_price_nzd_per_mwh_displayed"], abs=5e-4
    )
    assert evidence["state_comparison"]["fixed_state_bound_mismatch_count"] == 0
