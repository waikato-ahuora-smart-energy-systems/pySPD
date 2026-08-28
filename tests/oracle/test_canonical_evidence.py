from __future__ import annotations

import math

import pytest

from tools.oracle.canonical import (
    CanonicalGdxEvidence,
    LinearMatrixEvidence,
    LinearMatrixValidator,
    MatrixColumn,
    MatrixEntry,
    MatrixRow,
    SymbolSnapshot,
    canonical_value,
)


def test_canonical_value_preserves_numeric_identity() -> None:
    assert canonical_value(1.5) == {"kind": "finite", "hex": "0x1.8000000000000p+0"}
    assert canonical_value(0.0) == {"kind": "finite", "hex": "0x0.0p+0"}
    assert canonical_value(-0.0) == {"kind": "eps"}
    assert canonical_value(math.inf) == {"kind": "posinf"}
    assert canonical_value(-math.inf) == {"kind": "neginf"}
    assert canonical_value(3) == {"kind": "integer", "value": 3}
    assert canonical_value("NI") == {"kind": "string", "value": "NI"}


def test_gdx_evidence_hashes_order_and_content_separately() -> None:
    first = SymbolSnapshot(
        name="demand",
        kind="parameter",
        subtype=None,
        domain=("node",),
        description="MW",
        columns=("node", "value"),
        records=(("B", 2.0), ("A", 1.0)),
    )
    reordered = SymbolSnapshot(
        name="demand",
        kind="parameter",
        subtype=None,
        domain=("node",),
        description="MW",
        columns=("node", "value"),
        records=(("A", 1.0), ("B", 2.0)),
    )

    evidence_a = CanonicalGdxEvidence.from_snapshots((first,), ("B", "A"))
    evidence_b = CanonicalGdxEvidence.from_snapshots((reordered,), ("A", "B"))

    assert evidence_a.symbols[0].content_sha256 == evidence_b.symbols[0].content_sha256
    assert evidence_a.symbols[0].ordered_sha256 != evidence_b.symbols[0].ordered_sha256
    assert evidence_a.uels_ordered_sha256 != evidence_b.uels_ordered_sha256


def test_matrix_evidence_is_order_independent_and_rejects_duplicates() -> None:
    rows = (
        MatrixRow("balance", lower=10.0, upper=10.0, marginal=25.0),
        MatrixRow("capacity", lower=-math.inf, upper=8.0, marginal=0.0),
    )
    columns = (
        MatrixColumn(
            "generation",
            lower=0.0,
            upper=math.inf,
            objective=-20.0,
            level=10.0,
            reduced_cost=0.0,
            discrete_type="continuous",
        ),
    )
    entries = (
        MatrixEntry("capacity", "generation", 1.0),
        MatrixEntry("balance", "generation", 1.0),
    )

    first = LinearMatrixEvidence.build(rows, columns, entries, sense="maximize")
    second = LinearMatrixEvidence.build(
        tuple(reversed(rows)),
        columns,
        tuple(reversed(entries)),
        sense="maximize",
    )

    assert first.logical_sha256 == second.logical_sha256
    assert first.nonzero_count == 2

    with pytest.raises(ValueError, match="duplicate matrix coefficient"):
        LinearMatrixEvidence.build(
            rows,
            columns,
            (entries[0], entries[0]),
            sense="maximize",
        )


def test_matrix_validator_checks_activity_bounds_and_stationarity() -> None:
    matrix = LinearMatrixEvidence.build(
        rows=(MatrixRow("balance", 10.0, 10.0, 20.0, level=10.0),),
        columns=(MatrixColumn("generation", 0.0, 20.0, 20.0, 10.0, 0.0, "continuous"),),
        entries=(MatrixEntry("balance", "generation", 1.0),),
        sense="maximize",
    )

    validation = LinearMatrixValidator.validate(matrix, absolute_tolerance=1e-9)

    assert validation.passed
    assert validation.max_activity_delta == pytest.approx(0.0)
    assert validation.max_row_bound_violation == pytest.approx(0.0)
    assert validation.max_column_bound_violation == pytest.approx(0.0)
    assert validation.max_stationarity_residual == pytest.approx(0.0)


def test_matrix_validator_separates_free_zero_objective_stationarity() -> None:
    free_angle = LinearMatrixEvidence.build(
        rows=(MatrixRow("angle_reference", 0.0, 0.0, 5e-8, level=0.0),),
        columns=(
            MatrixColumn(
                "angle",
                -math.inf,
                math.inf,
                0.0,
                0.0,
                0.0,
                "continuous",
            ),
        ),
        entries=(MatrixEntry("angle_reference", "angle", 1000.0),),
        sense="maximize",
    )

    validation = LinearMatrixValidator.validate(
        free_angle,
        absolute_tolerance=1e-7,
        free_zero_objective_stationarity_tolerance=1e-4,
    )

    assert validation.passed
    assert validation.max_stationarity_residual == pytest.approx(5e-5)
    assert validation.max_scaled_stationarity_residual == pytest.approx(5e-8)
    assert validation.max_regular_stationarity_residual == pytest.approx(0.0)
    assert validation.max_free_zero_objective_stationarity_residual == pytest.approx(
        5e-5
    )
    assert validation.free_zero_objective_stationarity_tolerance == pytest.approx(1e-4)

    bounded_angle = LinearMatrixEvidence.build(
        rows=free_angle.rows,
        columns=(
            MatrixColumn("angle", -1.0, 1.0, 0.0, 0.0, 0.0, "continuous"),
        ),
        entries=free_angle.entries,
        sense="maximize",
    )

    bounded_validation = LinearMatrixValidator.validate(
        bounded_angle,
        absolute_tolerance=1e-7,
        free_zero_objective_stationarity_tolerance=1e-4,
    )

    assert not bounded_validation.passed
    assert bounded_validation.max_regular_stationarity_residual == pytest.approx(5e-5)
    assert bounded_validation.max_free_zero_objective_stationarity_residual == pytest.approx(
        0.0
    )
