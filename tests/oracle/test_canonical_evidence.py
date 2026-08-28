from __future__ import annotations

import math

import pytest

from tools.oracle.canonical import (
    CanonicalGdxEvidence,
    ConvertDictionaryReader,
    IncrementalMatrixTransforms,
    LinearMatrixEvidence,
    LinearMatrixValidator,
    MatrixColumn,
    MatrixEntry,
    MatrixRow,
    SemanticNameDictionary,
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
    assert first.structural_sha256 == second.structural_sha256
    assert first.nonzero_count == 2

    with pytest.raises(ValueError, match="duplicate matrix coefficient"):
        LinearMatrixEvidence.build(
            rows,
            columns,
            (entries[0], entries[0]),
            sense="maximize",
        )


def test_convert_dictionary_replaces_scalar_names_with_indexed_semantics() -> None:
    rows = ConvertDictionaryReader.mapping_records(
        "NodeBalance_EM",
        (("e1", "base", "01-NOV-2022 13:00", "ABY0111"),),
    )
    columns = ConvertDictionaryReader.mapping_records(
        "Generation_VM",
        (("x1", "base", "01-NOV-2022 13:00", "ARA2201 ARA0"),),
    )
    dictionary = SemanticNameDictionary.build(rows, columns)
    scalar = LinearMatrixEvidence.build(
        rows=(MatrixRow("e1", 10.0, 10.0, 20.0, level=10.0),),
        columns=(
            MatrixColumn("x1", 0.0, 20.0, 20.0, 10.0, 0.0, "continuous"),
        ),
        entries=(MatrixEntry("e1", "x1", 1.0),),
        sense="maximize",
    )

    semantic = dictionary.apply(scalar)

    assert semantic.rows[0].name == (
        'NodeBalance["base","01-NOV-2022 13:00","ABY0111"]'
    )
    assert semantic.columns[0].name == (
        'Generation["base","01-NOV-2022 13:00","ARA2201 ARA0"]'
    )
    assert semantic.entries[0].row == semantic.rows[0].name
    assert semantic.entries[0].column == semantic.columns[0].name
    assert semantic.logical_sha256 != scalar.logical_sha256


def test_convert_dictionary_is_fail_closed_for_missing_or_ambiguous_names() -> None:
    matrix = LinearMatrixEvidence.build(
        rows=(MatrixRow("e1", 0.0, 0.0, 0.0, level=0.0),),
        columns=(MatrixColumn("x1", 0.0, 1.0, 0.0, 0.0, 0.0, "continuous"),),
        entries=(),
        sense="maximize",
    )

    with pytest.raises(ValueError, match="does not cover matrix names"):
        SemanticNameDictionary.build((), ()).apply(matrix)
    with pytest.raises(ValueError, match="duplicate semantic row"):
        SemanticNameDictionary.build(
            (("e1", "Balance"), ("e2", "Balance")),
            (("x1", "Generation"),),
        )


def test_incremental_row_sign_and_split_dual_transforms_are_exact() -> None:
    row = MatrixRow("ranged", -2.0, 5.0, 3.0, level=4.0)
    entries = (MatrixEntry("ranged", "x", 2.5),)

    signed_row, signed_entries = IncrementalMatrixTransforms.signed_row(
        row, entries, -1
    )
    restored_row, restored_entries = IncrementalMatrixTransforms.signed_row(
        signed_row, signed_entries, -1
    )

    assert signed_row == MatrixRow("ranged", -5.0, 2.0, -3.0, level=-4.0)
    assert signed_entries == (MatrixEntry("ranged", "x", -2.5),)
    assert restored_row == row
    assert restored_entries == entries
    assert IncrementalMatrixTransforms.recombine_ranged_dual(2.0, 5.0) == 3.0
    with pytest.raises(ValueError, match="finite and non-negative"):
        IncrementalMatrixTransforms.recombine_ranged_dual(-1.0, 0.0)


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


def test_matrix_validator_checks_split_bound_duals_and_complementarity() -> None:
    valid = LinearMatrixEvidence.build(
        rows=(MatrixRow("ranged", 0.0, 10.0, 2.0, level=10.0),),
        columns=(
            MatrixColumn("x", -math.inf, math.inf, 2.0, 10.0, 0.0, "continuous"),
        ),
        entries=(MatrixEntry("ranged", "x", 1.0),),
        sense="maximize",
    )

    valid_result = LinearMatrixValidator.validate(valid)

    assert valid_result.passed
    assert valid_result.max_row_complementarity == pytest.approx(0.0)
    assert valid_result.max_dual_sign_violation == pytest.approx(0.0)

    wrong_side = LinearMatrixEvidence.build(
        rows=(MatrixRow("ranged", 0.0, 10.0, -2.0, level=10.0),),
        columns=(
            MatrixColumn("x", -math.inf, math.inf, -2.0, 10.0, 0.0, "continuous"),
        ),
        entries=valid.entries,
        sense="maximize",
    )

    wrong_result = LinearMatrixValidator.validate(wrong_side)

    assert not wrong_result.passed
    assert wrong_result.max_row_complementarity == pytest.approx(20.0)
    assert wrong_result.max_scaled_complementarity > 1e-6


def test_matrix_validator_rejects_dual_on_a_missing_bound_side() -> None:
    lower_bounded = LinearMatrixEvidence.build(
        rows=(),
        columns=(MatrixColumn("x", 0.0, math.inf, 2.0, 0.0, 2.0, "continuous"),),
        entries=(),
        sense="maximize",
    )

    result = LinearMatrixValidator.validate(lower_bounded)

    assert not result.passed
    assert result.max_stationarity_residual == pytest.approx(0.0)
    assert result.max_dual_sign_violation == pytest.approx(2.0)
