"""Probity-first contracts for Gate 12 end-to-end evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tools.gate12.evidence import (
    REQUIRED_E2E_SURFACES,
    AffectedIntervalIdentity,
    AffectedIntervalManifest,
    CaseSurfaceArtifact,
    DegeneracyCertificate,
    E2ECaseEvidenceBuilder,
    E2EDayEvidenceBuilder,
    EvidenceContractError,
    Observable,
    ParityComparator,
    SolverProfile,
    TwoSidedDegeneracyEvidence,
)


def _dates() -> tuple[str, ...]:
    values = (
        f"2024{month:02d}{day:02d}"
        for month in range(1, 13)
        for day in range(1, 13)
    )
    return tuple(values)[:139]


def _hashes() -> dict[str, str]:
    return {trading_date: f"{position:064x}" for position, trading_date in enumerate(_dates(), 1)}


def _identities(count: int = 546) -> tuple[AffectedIntervalIdentity, ...]:
    dates = _dates()
    hashes = _hashes()
    return tuple(
        AffectedIntervalIdentity(
            case_id=f"5101{position:016d}",
            date_time=f"{dates[position % len(dates)]}T{position % 288:03d}",
            trading_period=f"TP{position % 50 + 1}",
            trading_date=dates[position % len(dates)],
            source_sha256=hashes[dates[position % len(dates)]],
            discovery_rationale="pinned-v5.0.2 solved shortfall transfer",
        )
        for position in range(count)
    )


def test_interval_manifest_requires_exact_hash_bound_population() -> None:
    manifest = AffectedIntervalManifest(
        source_release="v5.0.4",
        reference_commit="3360a91",
        identities=_identities(),
    )

    manifest.validate(expected_source_hashes=_hashes())

    with pytest.raises(
        EvidenceContractError,
        match="REQ-G12-POPULATION: expected exactly 546 unique identities",
    ):
        replace(manifest, identities=_identities(427)).validate(
            expected_source_hashes=_hashes()
        )


def test_case_evidence_builder_hashes_every_raw_surface_artifact() -> None:
    artifacts = tuple(
        CaseSurfaceArtifact(name, f"{name}\n".encode(), passed=True)
        for name in REQUIRED_E2E_SURFACES
    )

    evidence = E2ECaseEvidenceBuilder().build(
        case_id="case-1",
        trading_date="20221106",
        source_sha256="a" * 64,
        solver_profile=SolverProfile.PORTABLE_SCIP_HIGHS,
        artifacts=artifacts,
    )

    evidence.validate()
    assert set(evidence.surface_sha256) == set(REQUIRED_E2E_SURFACES)
    assert len(set(evidence.surface_sha256.values())) == len(artifacts)


def test_day_evidence_builder_exposes_repeat_or_resume_drift() -> None:
    builder = E2EDayEvidenceBuilder()
    evidence = builder.build(
        trading_date="20221106",
        category="normal",
        source_sha256="a" * 64,
        case_order=b"case-1\n",
        output=b"output\n",
        repeat_output=b"output\n",
        resumed_output=b"changed\n",
        report=b"report\n",
        passed=True,
    )

    with pytest.raises(EvidenceContractError, match="repeated and resumed"):
        evidence.validate()


def test_interval_manifest_rejects_duplicate_and_unbound_identity() -> None:
    identities = list(_identities())
    identities[-1] = identities[0]
    manifest = AffectedIntervalManifest("v5.0.4", "3360a91", tuple(identities))

    with pytest.raises(EvidenceContractError, match="unique identities"):
        manifest.validate(expected_source_hashes=_hashes())

    identities = list(_identities())
    identities[0] = replace(identities[0], source_sha256="f" * 64)
    manifest = AffectedIntervalManifest("v5.0.4", "3360a91", tuple(identities))
    with pytest.raises(EvidenceContractError, match="Gate 1 source hash"):
        manifest.validate(expected_source_hashes=_hashes())


def test_comparator_fails_closed_for_missing_and_material_observables() -> None:
    expected = (
        Observable("case-1", "node_price", ("TP1", "BEN2201"), 100.0),
        Observable("case-1", "reserve_price", ("TP1", "NI", "FIR"), 0.11),
    )
    comparator = ParityComparator(absolute_tolerance=1e-6)

    missing = comparator.compare(expected, expected[:1])
    assert not missing.passed
    assert missing.missing_identities == (
        ("case-1", "reserve_price", ("TP1", "NI", "FIR")),
    )

    changed = comparator.compare(
        expected,
        (
            expected[0],
            replace(expected[1], value=0.50),
        ),
    )
    assert not changed.passed
    assert changed.maximum_absolute_error == pytest.approx(0.39)
    assert changed.unresolved_material_count == 1


def test_degeneracy_certificate_is_case_specific_and_evidence_bound() -> None:
    expected = (Observable("case-1", "node_price", ("TP1", "BEN2201"), 100.0),)
    actual = (replace(expected[0], value=101.0),)
    certificate = DegeneracyCertificate(
        case_id="case-1",
        observable_kind="node_price",
        identity=("TP1", "BEN2201"),
        reference_value=100.0,
        candidate_value=101.0,
        method="common-optimal-face+kkt+finite-difference",
        evidence_sha256="a" * 64,
        passed=True,
    )

    report = ParityComparator(absolute_tolerance=1e-6).compare(
        expected, actual, certificates=(certificate,)
    )
    assert report.passed
    assert report.certified_alternative_count == 1

    wrong_case = replace(certificate, case_id="case-2")
    report = ParityComparator(absolute_tolerance=1e-6).compare(
        expected, actual, certificates=(wrong_case,)
    )
    assert not report.passed
    assert report.unresolved_material_count == 1


def test_strict_and_portable_profiles_cannot_be_conflated() -> None:
    assert SolverProfile.STRICT_CPLEX.value == "strict-cplex"
    assert SolverProfile.PORTABLE_SCIP_HIGHS.value == "portable-scip-highs"
    assert SolverProfile.STRICT_CPLEX is not SolverProfile.PORTABLE_SCIP_HIGHS


def test_two_sided_kink_evidence_issues_a_case_specific_certificate() -> None:
    evidence = TwoSidedDegeneracyEvidence(
        case_id="case-1",
        observable_kind="reserve_price",
        identity=("TP30", "NI", "FIR"),
        reference_value=0.11,
        candidate_value=0.01,
        negative_perturbation_derivative=0.1100004,
        positive_perturbation_derivative=0.0100136,
        derivative_tolerance=2e-5,
        common_objective_absolute_error=4.5e-5,
        common_objective_tolerance=1e-4,
        reference_kkt_passed=True,
        candidate_kkt_passed=True,
    )

    certificate = evidence.certificate()

    assert certificate.passed
    assert certificate.method == "common-optimal-face+kkt+two-sided-finite-difference"
    assert len(certificate.evidence_sha256) == 64
    expected = (
        Observable("case-1", "reserve_price", ("TP30", "NI", "FIR"), 0.11),
    )
    actual = (replace(expected[0], value=0.01),)
    assert ParityComparator(absolute_tolerance=1e-6).compare(
        expected, actual, certificates=(certificate,)
    ).passed


def test_two_sided_kink_evidence_rejects_value_outside_subgradient_interval() -> None:
    evidence = TwoSidedDegeneracyEvidence(
        case_id="case-1",
        observable_kind="reserve_price",
        identity=("TP30", "NI", "FIR"),
        reference_value=0.50,
        candidate_value=0.01,
        negative_perturbation_derivative=0.11,
        positive_perturbation_derivative=0.01,
        derivative_tolerance=1e-5,
        common_objective_absolute_error=0.0,
        common_objective_tolerance=1e-4,
        reference_kkt_passed=True,
        candidate_kkt_passed=True,
    )

    assert not evidence.certificate().passed
