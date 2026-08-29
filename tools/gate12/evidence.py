"""Fail-closed, machine-readable contracts for Gate 12 parity evidence."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

EXPECTED_AFFECTED_INTERVALS = 546
EXPECTED_TRADING_DATES = 139
_SHA256 = re.compile(r"[0-9a-f]{64}")

type ObservableIdentity = tuple[str, str, tuple[str, ...]]


class EvidenceContractError(ValueError):
    """Raised when evidence cannot support the declared Gate 12 claim."""


class SolverProfile(str, Enum):
    """Solver profiles whose claims and evidence must remain separate."""

    STRICT_CPLEX = "strict-cplex"
    PORTABLE_SCIP_HIGHS = "portable-scip-highs"


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
