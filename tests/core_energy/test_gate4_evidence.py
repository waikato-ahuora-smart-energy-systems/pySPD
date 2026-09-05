from __future__ import annotations

import json
from pathlib import Path


def _read(name: str) -> dict[str, object]:
    return json.loads(Path("docs/gate-4", name).read_text(encoding="utf-8"))


def test_gate4_gams_matrix_projection_is_exact() -> None:
    evidence = _read("oracle-matrix-parity.json")
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
    python = evidence["python"]
    gams = evidence["gams"]
    assert python == gams
    assert python["row_count"] == 882
    assert python["column_count"] == 11_632
    assert python["nonzero_count"] == 12_892


def test_gate4_oracle_covers_demand_rows_and_objective_constant() -> None:
    evidence = _read("oracle-demand-objective-parity.json")

    assert evidence["passed"] is True
    assert evidence["coverage"] == {
        "DemBidDefintion": {"gams_rows": 2, "python_rows": 2},
        "DemBidDiscrete": {"gams_rows": 1, "python_rows": 1},
    }
    assert evidence["objective_constant"]["passed"] is True
    assert evidence["objective_constant"]["difference_nzd"] <= 1e-7


def test_gate4_full_case_residual_objective_and_price_evidence_passes() -> None:
    evidence = _read("solve-price-validation.json")
    assert evidence["passed"] is True
    assert evidence["solver"]["status"] == "optimal"
    assert evidence["solver"]["termination"] == "optimal"
    assert evidence["validation"]["maximum_primal_residual_mw"] <= 1e-7
    assert evidence["validation"]["maximum_bound_violation_mw"] <= 1e-7
    assert evidence["validation"]["maximum_objective_component_error_nzd"] <= 1e-7
    assert evidence["pricing"]["maximum_absolute_error"] <= 2e-5
    assert evidence["pricing"]["unit"] == "NZD/MWh"


def test_gate4_preprocessing_extension_retains_oracle_parity() -> None:
    evidence = _read("preprocessing-extension-parity.json")
    assert evidence["passed"] is True
    assert evidence["comparison_count"] == 68
    assert all(item["passed"] for item in evidence["comparisons"])
