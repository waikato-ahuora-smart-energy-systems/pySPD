"""Fail-closed, machine-readable contracts for Gate 12 parity evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum

EXPECTED_AFFECTED_INTERVALS = 546
EXPECTED_TRADING_DATES = 139
_SHA256 = re.compile(r"[0-9a-f]{64}")

REQUIRED_E2E_SURFACES = frozenset(
    {
        "case-selection",
        "state-transition",
        "primary-physics",
        "primary-objective",
        "fixed-discrete-pricing-state",
        "raw-bus-price",
        "repaired-bus-price",
        "node-price",
        "reserve-price",
        "publication-seconds",
        "rounded-published-output",
        "report-field",
    }
)
REQUIRED_E2E_DAY_CATEGORIES = frozenset(
    {
        "normal",
        "outage",
        "high-negative-price",
        "scarcity",
        "islanding",
        "dst-46",
        "dst-50",
    }
)

type ObservableIdentity = tuple[str, str, tuple[str, ...]]


class EvidenceContractError(ValueError):
    """Raised when evidence cannot support the declared Gate 12 claim."""


class SolverProfile(str, Enum):
    """Solver profiles whose claims and evidence must remain separate."""

    STRICT_CPLEX = "strict-cplex"
    PORTABLE_SCIP_HIGHS = "portable-scip-highs"


@dataclass(frozen=True)
class E2ECaseEvidence:
    """Hash index for every required observable surface of one replayed case."""

    case_id: str
    trading_date: str
    source_sha256: str
    solver_profile: SolverProfile
    surface_sha256: dict[str, str]
    unresolved_material_count: int
    passed: bool

    def validate(self) -> None:
        if not self.case_id.strip() or not re.fullmatch(r"[0-9]{8}", self.trading_date):
            raise EvidenceContractError(
                "REQ-G12-E2E: invalid case or trading-date identity"
            )
        if not _SHA256.fullmatch(self.source_sha256):
            raise EvidenceContractError("REQ-G12-E2E: invalid case source hash")
        if set(self.surface_sha256) != set(REQUIRED_E2E_SURFACES) or any(
            not _SHA256.fullmatch(value) for value in self.surface_sha256.values()
        ):
            raise EvidenceContractError(
                "REQ-G12-E2E: incomplete or invalid case surface evidence"
            )
        if self.unresolved_material_count != 0 or not self.passed:
            raise EvidenceContractError(
                "REQ-G12-E2E: case has an unresolved material discrepancy"
            )


@dataclass(frozen=True)
class E2EDayEvidence:
    """Whole-day output evidence including repeat and resume equivalence."""

    trading_date: str
    category: str
    source_sha256: str
    case_order_sha256: str
    output_sha256: str
    repeat_output_sha256: str
    resumed_output_sha256: str
    report_sha256: str
    passed: bool

    def validate(self) -> None:
        hashes = (
            self.source_sha256,
            self.case_order_sha256,
            self.output_sha256,
            self.repeat_output_sha256,
            self.resumed_output_sha256,
            self.report_sha256,
        )
        if (
            not re.fullmatch(r"[0-9]{8}", self.trading_date)
            or self.category not in REQUIRED_E2E_DAY_CATEGORIES
            or any(not _SHA256.fullmatch(value) for value in hashes)
        ):
            raise EvidenceContractError(
                "REQ-G12-E2E: invalid representative-day evidence"
            )
        if not (
            self.output_sha256
            == self.repeat_output_sha256
            == self.resumed_output_sha256
        ):
            raise EvidenceContractError(
                "REQ-G12-E2E: repeated and resumed day outputs differ"
            )
        if not self.passed:
            raise EvidenceContractError(
                "REQ-G12-E2E: representative day did not pass"
            )


@dataclass(frozen=True)
class Gate12EvidenceIndex:
    """Fail-closed closure index across cases, days, profiles, and discrepancies."""

    affected_manifest_sha256: str
    cases: tuple[E2ECaseEvidence, ...]
    representative_days: tuple[E2EDayEvidence, ...]
    portable_profile_executed: bool
    strict_profile_executed: bool
    unresolved_material_count: int

    def validate(
        self,
        *,
        expected_case_ids: set[str],
        expected_source_hashes: dict[str, str],
    ) -> None:
        if not _SHA256.fullmatch(self.affected_manifest_sha256):
            raise EvidenceContractError(
                "REQ-G12-E2E: invalid affected-manifest hash"
            )
        case_ids = [case.case_id for case in self.cases]
        if (
            len(self.cases) != EXPECTED_AFFECTED_INTERVALS
            or len(set(case_ids)) != len(case_ids)
            or set(case_ids) != expected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-E2E: case evidence must cover exactly 546 identities"
            )
        if len(expected_source_hashes) != EXPECTED_TRADING_DATES:
            raise EvidenceContractError(
                "REQ-G12-E2E: expected exactly 139 source hashes"
            )
        for case in self.cases:
            case.validate()
            if case.solver_profile is not SolverProfile.PORTABLE_SCIP_HIGHS:
                raise EvidenceContractError(
                    "REQ-G12-E2E: affected replay must use the portable profile"
                )
            if expected_source_hashes.get(case.trading_date) != case.source_sha256:
                raise EvidenceContractError(
                    "REQ-G12-E2E: case evidence source hash mismatch"
                )
        categories = {day.category for day in self.representative_days}
        if categories != set(REQUIRED_E2E_DAY_CATEGORIES):
            raise EvidenceContractError(
                "REQ-G12-E2E: representative day categories are incomplete"
            )
        for day in self.representative_days:
            day.validate()
        if not self.portable_profile_executed:
            raise EvidenceContractError(
                "REQ-G12-E2E: portable profile was not executed"
            )
        if not self.strict_profile_executed:
            raise EvidenceContractError(
                "REQ-G12-E2E: strict profile was not executed"
            )
        if self.unresolved_material_count != 0:
            raise EvidenceContractError(
                "REQ-G12-E2E: discrepancy register is not empty"
            )


@dataclass(frozen=True)
class AffectedIntervalIdentity:
    """One solved shortfall-transfer identity bound to its raw source."""

    case_id: str
    date_time: str
    trading_period: str
    trading_date: str
    source_sha256: str
    discovery_rationale: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.case_id, self.date_time, self.trading_period)


@dataclass(frozen=True)
class AffectedIntervalManifest:
    """The complete Authority-declared v5.0.4 defect population."""

    source_release: str
    reference_commit: str
    identities: tuple[AffectedIntervalIdentity, ...]

    def validate(self, *, expected_source_hashes: dict[str, str]) -> None:
        unique = {identity.key for identity in self.identities}
        if (
            len(self.identities) != EXPECTED_AFFECTED_INTERVALS
            or len(unique) != EXPECTED_AFFECTED_INTERVALS
        ):
            raise EvidenceContractError(
                "REQ-G12-POPULATION: expected exactly 546 unique identities"
            )
        if len(expected_source_hashes) != EXPECTED_TRADING_DATES:
            raise EvidenceContractError(
                "REQ-G12-POPULATION: expected exactly 139 Gate 1 source hashes"
            )
        if any(not _SHA256.fullmatch(value) for value in expected_source_hashes.values()):
            raise EvidenceContractError(
                "REQ-G12-POPULATION: invalid Gate 1 source hash"
            )
        covered_dates = {identity.trading_date for identity in self.identities}
        if covered_dates != set(expected_source_hashes):
            raise EvidenceContractError(
                "REQ-G12-POPULATION: identities must cover all 139 trading dates"
            )
        for identity in self.identities:
            expected_hash = expected_source_hashes.get(identity.trading_date)
            if identity.source_sha256 != expected_hash:
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: identity does not match its Gate 1 source hash"
                )
            if not identity.discovery_rationale.strip():
                raise EvidenceContractError(
                    "REQ-G12-POPULATION: identity lacks a discovery rationale"
                )


@dataclass(frozen=True)
class Observable:
    """One case-scoped output value on a named E2E comparison surface."""

    case_id: str
    kind: str
    identity: tuple[str, ...]
    value: float

    @property
    def key(self) -> ObservableIdentity:
        return (self.case_id, self.kind, self.identity)


@dataclass(frozen=True)
class DegeneracyCertificate:
    """Evidence-bound permission for one solver-sensitive alternative value."""

    case_id: str
    observable_kind: str
    identity: tuple[str, ...]
    reference_value: float
    candidate_value: float
    method: str
    evidence_sha256: str
    passed: bool

    @property
    def key(self) -> ObservableIdentity:
        return (self.case_id, self.observable_kind, self.identity)

    def valid_for(self, expected: Observable, actual: Observable) -> bool:
        return bool(
            self.passed
            and self.key == expected.key == actual.key
            and self.reference_value == expected.value
            and self.candidate_value == actual.value
            and self.method.strip()
            and _SHA256.fullmatch(self.evidence_sha256)
        )


@dataclass(frozen=True)
class TwoSidedDegeneracyEvidence:
    """Prove that two reported prices are valid subgradients at one LP kink."""

    case_id: str
    observable_kind: str
    identity: tuple[str, ...]
    reference_value: float
    candidate_value: float
    negative_perturbation_derivative: float
    positive_perturbation_derivative: float
    derivative_tolerance: float
    common_objective_absolute_error: float
    common_objective_tolerance: float
    reference_kkt_passed: bool
    candidate_kkt_passed: bool

    def certificate(self) -> DegeneracyCertificate:
        numeric = (
            self.reference_value,
            self.candidate_value,
            self.negative_perturbation_derivative,
            self.positive_perturbation_derivative,
            self.derivative_tolerance,
            self.common_objective_absolute_error,
            self.common_objective_tolerance,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise EvidenceContractError(
                "REQ-G12-DEGENERACY: evidence values must be finite"
            )
        if self.derivative_tolerance < 0.0 or self.common_objective_tolerance < 0.0:
            raise EvidenceContractError(
                "REQ-G12-DEGENERACY: tolerances must be non-negative"
            )
        lower = min(
            self.negative_perturbation_derivative,
            self.positive_perturbation_derivative,
        )
        upper = max(
            self.negative_perturbation_derivative,
            self.positive_perturbation_derivative,
        )
        within_subgradient = all(
            lower - self.derivative_tolerance
            <= value
            <= upper + self.derivative_tolerance
            for value in (self.reference_value, self.candidate_value)
        )
        passed = bool(
            within_subgradient
            and self.common_objective_absolute_error
            <= self.common_objective_tolerance
            and self.reference_kkt_passed
            and self.candidate_kkt_passed
        )
        payload = {
            "case_id": self.case_id,
            "observable_kind": self.observable_kind,
            "identity": list(self.identity),
            "reference_value": self.reference_value.hex(),
            "candidate_value": self.candidate_value.hex(),
            "negative_perturbation_derivative": (
                self.negative_perturbation_derivative.hex()
            ),
            "positive_perturbation_derivative": (
                self.positive_perturbation_derivative.hex()
            ),
            "derivative_tolerance": self.derivative_tolerance.hex(),
            "common_objective_absolute_error": (
                self.common_objective_absolute_error.hex()
            ),
            "common_objective_tolerance": self.common_objective_tolerance.hex(),
            "reference_kkt_passed": self.reference_kkt_passed,
            "candidate_kkt_passed": self.candidate_kkt_passed,
            "passed": passed,
        }
        evidence_sha256 = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return DegeneracyCertificate(
            case_id=self.case_id,
            observable_kind=self.observable_kind,
            identity=self.identity,
            reference_value=self.reference_value,
            candidate_value=self.candidate_value,
            method="common-optimal-face+kkt+two-sided-finite-difference",
            evidence_sha256=evidence_sha256,
            passed=passed,
        )


@dataclass(frozen=True)
class ParityComparison:
    """Complete result of an identity-strict observable comparison."""

    passed: bool
    expected_count: int
    actual_count: int
    missing_identities: tuple[ObservableIdentity, ...]
    extra_identities: tuple[ObservableIdentity, ...]
    maximum_absolute_error: float
    unresolved_material_count: int
    certified_alternative_count: int


class ParityComparator:
    """Compare E2E values without hiding missing fields or material deltas."""

    def __init__(self, *, absolute_tolerance: float) -> None:
        if not math.isfinite(absolute_tolerance) or absolute_tolerance < 0.0:
            raise EvidenceContractError(
                "REQ-G12-COMPARATOR: tolerance must be finite and non-negative"
            )
        self.absolute_tolerance = absolute_tolerance

    def compare(
        self,
        expected: tuple[Observable, ...],
        actual: tuple[Observable, ...],
        *,
        certificates: tuple[DegeneracyCertificate, ...] = (),
    ) -> ParityComparison:
        expected_by_key = self._index(expected, side="expected")
        actual_by_key = self._index(actual, side="actual")
        certificate_by_key = self._certificates(certificates)
        missing = tuple(sorted(set(expected_by_key) - set(actual_by_key)))
        extra = tuple(sorted(set(actual_by_key) - set(expected_by_key)))
        maximum_error = 0.0
        unresolved = 0
        certified = 0
        for key in sorted(set(expected_by_key) & set(actual_by_key)):
            reference = expected_by_key[key]
            candidate = actual_by_key[key]
            error = abs(reference.value - candidate.value)
            maximum_error = max(maximum_error, error)
            if error <= self.absolute_tolerance:
                continue
            certificate = certificate_by_key.get(key)
            if certificate is not None and certificate.valid_for(reference, candidate):
                certified += 1
            else:
                unresolved += 1
        passed = not missing and not extra and unresolved == 0
        return ParityComparison(
            passed=passed,
            expected_count=len(expected),
            actual_count=len(actual),
            missing_identities=missing,
            extra_identities=extra,
            maximum_absolute_error=maximum_error,
            unresolved_material_count=unresolved,
            certified_alternative_count=certified,
        )

    @staticmethod
    def _index(
        observations: tuple[Observable, ...], *, side: str
    ) -> dict[ObservableIdentity, Observable]:
        indexed: dict[ObservableIdentity, Observable] = {}
        for observation in observations:
            if not math.isfinite(observation.value):
                raise EvidenceContractError(
                    f"REQ-G12-COMPARATOR: {side} value must be finite"
                )
            if observation.key in indexed:
                raise EvidenceContractError(
                    f"REQ-G12-COMPARATOR: duplicate {side} observable identity"
                )
            indexed[observation.key] = observation
        return indexed

    @staticmethod
    def _certificates(
        certificates: tuple[DegeneracyCertificate, ...],
    ) -> dict[ObservableIdentity, DegeneracyCertificate]:
        indexed: dict[ObservableIdentity, DegeneracyCertificate] = {}
        for certificate in certificates:
            if certificate.key in indexed:
                raise EvidenceContractError(
                    "REQ-G12-COMPARATOR: duplicate degeneracy certificate identity"
                )
            indexed[certificate.key] = certificate
        return indexed
