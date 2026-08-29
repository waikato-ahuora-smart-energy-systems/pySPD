from __future__ import annotations

import json
from pathlib import Path


def test_gate6_exact_gams_hvdc_matrix_evidence_is_closed() -> None:
    evidence = json.loads(
        Path("docs/gate-6/oracle-matrix-parity.json").read_text()
    )
    assert evidence["passed"] is True
    assert evidence["differences"] == {
        "coefficient_mismatches": 0,
        "column_mismatches": 0,
        "extra_columns": 0,
        "extra_nonzeros": 0,
        "extra_rows": 0,
        "missing_columns": 0,
        "missing_nonzeros": 0,
        "missing_rows": 0,
        "row_bound_mismatches": 0,
    }
    assert evidence["python"] == evidence["gams"]


def test_gate6_solve_price_audit_and_independent_validation_are_closed() -> None:
    evidence = json.loads(
        Path("docs/gate-6/solve-price-validation.json").read_text()
    )
    assert evidence["passed"] is True
    assert evidence["state_machine"]["primary_status"] == "optimal"
    assert evidence["state_machine"]["pricing_status"] == "optimal"
    assert evidence["independent_validation"]["passed"] is True
    assert evidence["pricing_model_audit"]["passed"] is True
    assert evidence["finite_difference_price"]["passed"] is True
