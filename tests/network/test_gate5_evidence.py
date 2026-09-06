from __future__ import annotations

import json
from pathlib import Path


def test_gate5_exact_gams_matrix_evidence_is_closed() -> None:
    evidence = json.loads(
        Path("private/docs/gate-5/oracle-matrix-parity.json").read_text()
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


def test_gate5_solve_price_and_independent_validation_evidence_is_closed() -> None:
    evidence = json.loads(
        Path("private/docs/gate-5/solve-price-validation.json").read_text()
    )
    assert evidence["passed"] is True
    assert evidence["solver"]["status"] == "optimal"
    assert evidence["independent_validation"]["passed"] is True
    assert evidence["finite_difference_price"]["passed"] is True
