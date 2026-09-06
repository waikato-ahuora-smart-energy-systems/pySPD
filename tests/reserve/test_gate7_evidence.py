from __future__ import annotations

import json
from pathlib import Path


def test_gate7_canonical_gams_reserve_matrix_is_exact() -> None:
    evidence = json.loads(Path("private/docs/gate-7/oracle-matrix-parity.json").read_text())
    assert evidence["passed"] is True
    assert evidence["python"] == evidence["gams"]
    assert evidence["differences"]["missing_columns"] == 0
    assert evidence["differences"]["extra_columns"] == 0
    assert evidence["differences"]["column_mismatches"] == 0
    assert evidence["differences"]["missing_rows"] == 0
    assert evidence["differences"]["extra_rows"] == 0
    assert evidence["differences"]["unmapped_pyomo_terms"] == 0


def test_gate7_full_solve_price_and_independent_validation_are_closed() -> None:
    evidence = json.loads(
        Path("private/docs/gate-7/solve-price-validation.json").read_text()
    )
    assert evidence["passed"] is True
    assert evidence["state_machine"]["primary_backend"] == "gams-scip"
    assert evidence["state_machine"]["primary_status"] == "optimal"
    assert evidence["state_machine"]["pricing_backend"] == "highs"
    assert evidence["state_machine"]["pricing_status"] == "optimal"
    assert evidence["pricing_model_audit"]["complete_fix_set"] is True
    assert evidence["pricing_model_audit"]["pricing_discrete_count"] == 0
    assert evidence["pricing_model_audit"]["pricing_sos_count"] == 0
    assert evidence["independent_validation"]["passed"] is True
    assert evidence["energy_price_finite_difference"]["passed"] is True
    assert evidence["reserve_price_finite_difference"]["passed"] is True
    assert evidence["economic_perturbations"] == {
        "effective_shared_reserve_ce_ece": 3e-5,
        "exact": True,
        "rtd_generation_change": 0.0005,
        "shared_nfr": 1e-5,
        "shared_reserve": 2e-5,
    }
