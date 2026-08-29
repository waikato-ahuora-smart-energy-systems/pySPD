"""Probity tests for the complete Gate 12 E2E evidence index."""

from __future__ import annotations

import pytest

from tools.gate12.evidence import (
    REQUIRED_E2E_DAY_CATEGORIES,
    REQUIRED_E2E_SURFACES,
    E2ECaseEvidence,
    E2EDayEvidence,
    EvidenceContractError,
    Gate12EvidenceIndex,
    SolverProfile,
)


def _case(index: int, *, surfaces: frozenset[str] = REQUIRED_E2E_SURFACES):
    return E2ECaseEvidence(
        case_id=f"case_{index}",
        trading_date=f"2022{index % 139:04d}",
        source_sha256=f"{index % 139 + 1:064x}",
        solver_profile=SolverProfile.PORTABLE_SCIP_HIGHS,
        surface_sha256={name: "a" * 64 for name in surfaces},
        unresolved_material_count=0,
        passed=True,
    )


def _day(category: str, index: int) -> E2EDayEvidence:
    return E2EDayEvidence(
        trading_date=f"2023{index:04d}",
        category=category,
        source_sha256="b" * 64,
        case_order_sha256="c" * 64,
        output_sha256="d" * 64,
        repeat_output_sha256="d" * 64,
        resumed_output_sha256="d" * 64,
        report_sha256="e" * 64,
        passed=True,
    )


def test_gate12_index_accepts_complete_zero_discrepancy_evidence() -> None:
    cases = tuple(_case(index) for index in range(546))
    days = tuple(
        _day(category, index)
        for index, category in enumerate(sorted(REQUIRED_E2E_DAY_CATEGORIES))
    )
    expected_hashes = {f"2022{index:04d}": f"{index + 1:064x}" for index in range(139)}
    index = Gate12EvidenceIndex(
        affected_manifest_sha256="f" * 64,
        code_sha256="1" * 64,
        dependency_sha256="2" * 64,
        portable_profile_evidence_sha256="3" * 64,
        strict_profile_evidence_sha256="4" * 64,
        discrepancy_register_sha256="5" * 64,
        cases=cases,
        representative_days=days,
        unresolved_material_count=0,
    )

    index.validate(
        expected_case_ids={case.case_id for case in cases},
        expected_source_hashes=expected_hashes,
    )


def test_case_evidence_rejects_a_missing_surface() -> None:
    missing = frozenset(sorted(REQUIRED_E2E_SURFACES)[:-1])

    with pytest.raises(EvidenceContractError, match="surface"):
        _case(0, surfaces=missing).validate()


@pytest.mark.parametrize(
    "change,match",
    [
        ({"strict_profile_evidence_sha256": None}, "strict"),
        ({"unresolved_material_count": 1}, "discrep"),
        ({"representative_days": ()}, "day categories"),
    ],
)
def test_gate12_index_fails_closed_at_closure(
    change: dict[str, object], match: str
) -> None:
    cases = tuple(_case(index) for index in range(546))
    values: dict[str, object] = {
        "affected_manifest_sha256": "f" * 64,
        "code_sha256": "1" * 64,
        "dependency_sha256": "2" * 64,
        "portable_profile_evidence_sha256": "3" * 64,
        "strict_profile_evidence_sha256": "4" * 64,
        "discrepancy_register_sha256": "5" * 64,
        "cases": cases,
        "representative_days": tuple(
            _day(category, index)
            for index, category in enumerate(sorted(REQUIRED_E2E_DAY_CATEGORIES))
        ),
        "unresolved_material_count": 0,
    }
    values.update(change)
    index = Gate12EvidenceIndex(**values)  # type: ignore[arg-type]

    with pytest.raises(EvidenceContractError, match=match):
        index.validate(
            expected_case_ids={case.case_id for case in cases},
            expected_source_hashes={
                f"2022{date_index:04d}": f"{date_index + 1:064x}"
                for date_index in range(139)
            },
        )
