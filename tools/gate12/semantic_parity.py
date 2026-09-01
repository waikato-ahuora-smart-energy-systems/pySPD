"""Compact, policy-bound semantic parity for canonical Gate 12 bundles."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from tools.gate12.bus_price_degeneracy import (
    BusPriceCaseCertificate,
    BusPriceDegeneracyResult,
)
from tools.gate12.canonical_diff import (
    CanonicalJsonDiffer,
    CanonicalValueDifference,
)
from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore
from tools.gate12.zero_flow_price_convention import (
    ZeroFlowPriceConventionResult,
)

SEMANTIC_PARITY_PROFILE = "gams-pyspd-semantic-tolerance-v2"
SEMANTIC_CERTIFIED_PARITY_PROFILE = "gams-pyspd-semantic-tolerance-bus-certified-v2"
SEMANTIC_ZERO_FLOW_CERTIFIED_PARITY_PROFILE = (
    "gams-pyspd-semantic-tolerance-zero-flow-certified-v2"
)
_EXACT_SURFACES = frozenset(
    {"case-selection", "publication-seconds", "state-transition"}
)
_ZERO_SPARSE_SURFACES = frozenset({"primary-physics", "rounded-published-output"})
_MAX_EXAMPLES = 20


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticParityPolicy:
    """Named tolerances and qualifications for the portable Gate 12 profile."""

    price_tolerance: float = 1e-4
    objective_tolerance: float = 1e-4
    physics_tolerance: float = 1e-8
    fixed_state_tolerance: float = 1e-8
    zero_sparsity_tolerance: float = 1e-12
    raw_price_sentinel: float = 500_000.0

    def __post_init__(self) -> None:
        values = (
            self.price_tolerance,
            self.objective_tolerance,
            self.physics_tolerance,
            self.fixed_state_tolerance,
            self.zero_sparsity_tolerance,
            self.raw_price_sentinel,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise EvidenceContractError(
                "REQ-G12-SEMANTIC: policy values must be finite and non-negative"
            )
        if self.raw_price_sentinel == 0.0:
            raise EvidenceContractError(
                "REQ-G12-SEMANTIC: raw-price sentinel must be non-zero"
            )

    def tolerance_for(self, surface: str) -> float:
        if surface == "fixed-discrete-pricing-state":
            return self.fixed_state_tolerance
        if surface == "primary-physics":
            return self.physics_tolerance
        if surface == "primary-objective":
            return self.objective_tolerance
        if surface in {
            "node-price",
            "raw-bus-price",
            "repaired-bus-price",
            "reserve-price",
            "rounded-published-output",
        }:
            return self.price_tolerance
        return 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": "portable-semantic-policy-v2",
            "price_tolerance": self.price_tolerance.hex(),
            "objective_tolerance": self.objective_tolerance.hex(),
            "physics_tolerance": self.physics_tolerance.hex(),
            "fixed_state_tolerance": self.fixed_state_tolerance.hex(),
            "zero_sparsity_tolerance": self.zero_sparsity_tolerance.hex(),
            "raw_price_sentinel": self.raw_price_sentinel.hex(),
            "primary_mip_objective_disposition": "qualified-diagnostic",
            "fixed_sos_disposition": "compare-active-support-not-weight",
            "report_field_disposition": "crosswalk-required",
        }


@dataclass(frozen=True, slots=True)
class SemanticSurfaceResult:
    """Compact semantic disposition for one canonical surface."""

    surface: str
    reference_sha256: str
    candidate_sha256: str
    observed_difference_count: int
    accepted_difference_count: int
    unresolved_difference_count: int
    maximum_absolute_error: float
    maximum_unresolved_absolute_error: float
    accepted_reason_counts: dict[str, int]
    unresolved_reason_counts: dict[str, int]
    unresolved_examples: tuple[CanonicalValueDifference, ...]

    @property
    def passed(self) -> bool:
        return self.unresolved_difference_count == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "surface": self.surface,
            "passed": self.passed,
            "reference_sha256": self.reference_sha256,
            "candidate_sha256": self.candidate_sha256,
            "observed_difference_count": self.observed_difference_count,
            "accepted_difference_count": self.accepted_difference_count,
            "unresolved_difference_count": self.unresolved_difference_count,
            "maximum_absolute_error": self.maximum_absolute_error.hex(),
            "maximum_unresolved_absolute_error": (
                self.maximum_unresolved_absolute_error.hex()
            ),
            "accepted_reason_counts": self.accepted_reason_counts,
            "unresolved_reason_counts": self.unresolved_reason_counts,
            "unresolved_examples": [
                difference.to_dict() for difference in self.unresolved_examples
            ],
        }


class SemanticCaseComparator:
    """Apply explicit semantic rules without weakening canonical identity."""

    def __init__(self, policy: SemanticParityPolicy) -> None:
        self.policy = policy
        self.differ = CanonicalJsonDiffer()

    def compare_surface(
        self,
        *,
        surface: str,
        reference: bytes,
        candidate: bytes,
        repaired_reference: bytes | None = None,
        repaired_candidate: bytes | None = None,
        bus_price_certificate: BusPriceCaseCertificate | None = None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None = None,
    ) -> SemanticSurfaceResult:
        if surface not in REQUIRED_E2E_SURFACES:
            raise EvidenceContractError(
                "REQ-G12-SEMANTIC: unsupported canonical surface"
            )
        if surface == "report-field" and reference != candidate:
            return self._report_crosswalk_required(reference, candidate)

        difference = self.differ.compare(reference, candidate)
        if difference.identical:
            return SemanticSurfaceResult(
                surface=surface,
                reference_sha256=difference.reference_sha256,
                candidate_sha256=difference.candidate_sha256,
                observed_difference_count=0,
                accepted_difference_count=0,
                unresolved_difference_count=0,
                maximum_absolute_error=0.0,
                maximum_unresolved_absolute_error=0.0,
                accepted_reason_counts={},
                unresolved_reason_counts={},
                unresolved_examples=(),
            )

        repaired_errors = self._repaired_errors(repaired_reference, repaired_candidate)
        accepted: Counter[str] = Counter()
        unresolved: Counter[str] = Counter()
        examples: list[CanonicalValueDifference] = []
        maximum_unresolved = 0.0
        for item in difference.differences:
            reason = self._accepted_reason(
                surface=surface,
                item=item,
                repaired_errors=repaired_errors,
                bus_price_certificate=bus_price_certificate,
                zero_flow_price_certificate=zero_flow_price_certificate,
            )
            if reason is not None:
                accepted[reason] += 1
                continue
            unresolved[self._unresolved_reason(surface, item)] += 1
            if item.absolute_error is not None:
                maximum_unresolved = max(maximum_unresolved, item.absolute_error)
            if len(examples) < _MAX_EXAMPLES:
                examples.append(item)
        return SemanticSurfaceResult(
            surface=surface,
            reference_sha256=difference.reference_sha256,
            candidate_sha256=difference.candidate_sha256,
            observed_difference_count=difference.unresolved_difference_count,
            accepted_difference_count=sum(accepted.values()),
            unresolved_difference_count=sum(unresolved.values()),
            maximum_absolute_error=difference.maximum_absolute_error,
            maximum_unresolved_absolute_error=maximum_unresolved,
            accepted_reason_counts=dict(sorted(accepted.items())),
            unresolved_reason_counts=dict(sorted(unresolved.items())),
            unresolved_examples=tuple(examples),
        )

    def _accepted_reason(
        self,
        *,
        surface: str,
        item: CanonicalValueDifference,
        repaired_errors: dict[tuple[str, ...], float | None],
        bus_price_certificate: BusPriceCaseCertificate | None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None,
    ) -> str | None:
        if surface in _EXACT_SURFACES:
            return None
        if (
            zero_flow_price_certificate is not None
            and item.kind == "changed"
            and item.absolute_error is not None
            and self._zero_flow_certifies(
                zero_flow_price_certificate, surface, item.path
            )
        ):
            return "zero-flow-load-derivative-certificate"
        if (
            surface in {"raw-bus-price", "repaired-bus-price"}
            and bus_price_certificate is not None
            and bus_price_certificate.passed
            and item.kind == "changed"
            and item.absolute_error is not None
        ):
            return "node-allocation-nullspace-certificate"
        if (
            surface == "primary-objective"
            and item.path == ("primary_mip_objective_nzd",)
            and item.absolute_error is not None
        ):
            return "qualified-primary-mip-diagnostic"
        if surface == "fixed-discrete-pricing-state" and self._same_sos_support(item):
            return "equivalent-sos-support"
        if surface == "raw-bus-price" and self._is_sentinel_difference(item):
            repaired_error = repaired_errors.get(item.path)
            if (
                repaired_error is not None
                and repaired_error <= self.policy.price_tolerance
            ):
                return "raw-sentinel-normalized"
        if (
            surface in _ZERO_SPARSE_SURFACES
            and item.kind in {"missing", "extra"}
            and self._structural_number(item) <= self.policy.zero_sparsity_tolerance
        ):
            return "sparse-zero"
        if (
            item.kind == "changed"
            and item.absolute_error is not None
            and item.absolute_error <= self.policy.tolerance_for(surface)
        ):
            return "within-tolerance"
        return None

    @staticmethod
    def _zero_flow_certifies(
        certificate: ZeroFlowPriceConventionResult,
        surface: str,
        path: tuple[str, ...],
    ) -> bool:
        def identity(segment: str) -> tuple[str, ...] | None:
            prefix = "identity="
            if not segment.startswith(prefix):
                return None
            try:
                value = json.loads(segment[len(prefix) :])
            except json.JSONDecodeError:
                return None
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                return None
            return tuple(value)

        if surface in {"raw-bus-price", "repaired-bus-price", "node-price"}:
            if len(path) != 2 or path[1] != "value":
                return False
            key = identity(path[0])
            if key is None or len(key) != 3:
                return False
            if surface == "node-price":
                return certificate.certifies_node(key[0], key[2])
            return certificate.certifies_bus(key[0], key[2])
        if surface == "rounded-published-output":
            if len(path) != 3 or path[0] != "energy" or path[2] != "value":
                return False
            key = identity(path[1])
            return bool(
                key is not None
                and len(key) == 2
                and certificate.certifies_publication(key[0], key[1])
            )
        return False

    def _same_sos_support(self, item: CanonicalValueDifference) -> bool:
        if (
            item.kind != "changed"
            or len(item.path) != 3
            or item.path[0] != "fixed_sos_members"
            or not item.path[1].startswith("identity=")
            or item.path[2] != "value"
        ):
            return False
        reference = CanonicalJsonDiffer._number(item.reference)
        candidate = CanonicalJsonDiffer._number(item.candidate)
        return bool(
            reference is not None
            and candidate is not None
            and abs(reference) > self.policy.zero_sparsity_tolerance
            and abs(candidate) > self.policy.zero_sparsity_tolerance
        )

    @staticmethod
    def _unresolved_reason(surface: str, item: CanonicalValueDifference) -> str:
        if surface in _EXACT_SURFACES:
            return "exact-mismatch"
        if item.kind in {"missing", "extra", "encoding"}:
            return f"structural-{item.kind}"
        if item.absolute_error is None:
            return "non-numeric-mismatch"
        return "above-tolerance"

    def _is_sentinel_difference(self, item: CanonicalValueDifference) -> bool:
        values = (
            CanonicalJsonDiffer._number(item.reference),
            CanonicalJsonDiffer._number(item.candidate),
        )
        return any(
            value is not None and abs(value) == self.policy.raw_price_sentinel
            for value in values
        )

    @staticmethod
    def _structural_number(item: CanonicalValueDifference) -> float:
        raw = item.reference if item.kind == "missing" else item.candidate
        number = CanonicalJsonDiffer._number(raw)
        return math.inf if number is None else abs(number)

    def _repaired_errors(
        self, reference: bytes | None, candidate: bytes | None
    ) -> dict[tuple[str, ...], float | None]:
        if reference is None or candidate is None:
            return {}
        reference_payload = CanonicalJsonDiffer._load(reference, side="reference")
        candidate_payload = CanonicalJsonDiffer._load(candidate, side="candidate")
        reference_leaves = self.differ._flatten(reference_payload)
        candidate_leaves = self.differ._flatten(candidate_payload)
        errors: dict[tuple[str, ...], float | None] = {}
        for path in set(reference_leaves) | set(candidate_leaves):
            if path not in reference_leaves or path not in candidate_leaves:
                errors[path] = None
                continue
            expected = reference_leaves[path]
            actual = candidate_leaves[path]
            errors[path] = (
                0.0
                if expected == actual
                else self.differ._absolute_error(expected, actual)
            )
        return errors

    @staticmethod
    def _report_crosswalk_required(
        reference: bytes, candidate: bytes
    ) -> SemanticSurfaceResult:
        example = CanonicalValueDifference(
            path=(),
            kind="schema",
            reference="Authority-vSPD-report-schema",
            candidate="PySPD-report-schema",
            absolute_error=None,
        )
        return SemanticSurfaceResult(
            surface="report-field",
            reference_sha256=hashlib.sha256(reference).hexdigest(),
            candidate_sha256=hashlib.sha256(candidate).hexdigest(),
            observed_difference_count=1,
            accepted_difference_count=0,
            unresolved_difference_count=1,
            maximum_absolute_error=0.0,
            maximum_unresolved_absolute_error=0.0,
            accepted_reason_counts={},
            unresolved_reason_counts={"report-crosswalk-required": 1},
            unresolved_examples=(example,),
        )


@dataclass(frozen=True, slots=True)
class SemanticCaseResult:
    """Semantic parity disposition for all twelve surfaces of one case."""

    case_id: str
    surfaces: dict[str, SemanticSurfaceResult]

    @property
    def passed(self) -> bool:
        return all(surface.passed for surface in self.surfaces.values())

    @property
    def unresolved_difference_count(self) -> int:
        return sum(
            surface.unresolved_difference_count for surface in self.surfaces.values()
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "unresolved_difference_count": self.unresolved_difference_count,
            "surfaces": {
                name: result.to_dict() for name, result in sorted(self.surfaces.items())
            },
        }


@dataclass(frozen=True, slots=True)
class SemanticReplayResult:
    """Hash-bound semantic comparison for one paired daily replay."""

    trading_date: str
    source_sha256: str
    work_item_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    profile: str
    bus_price_certificate_sha256: str | None
    zero_flow_price_certificate_sha256: str | None
    policy: SemanticParityPolicy
    cases: tuple[SemanticCaseResult, ...]
    logical_sha256: str

    @property
    def passed(self) -> bool:
        return bool(self.cases and all(case.passed for case in self.cases))

    @property
    def unresolved_difference_count(self) -> int:
        return sum(case.unresolved_difference_count for case in self.cases)

    @property
    def failed_surface_count(self) -> int:
        return sum(
            not surface.passed
            for case in self.cases
            for surface in case.surfaces.values()
        )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": self.profile,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "work_item_sha256": self.work_item_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "bus_price_certificate_sha256": self.bus_price_certificate_sha256,
            "zero_flow_price_certificate_sha256": (
                self.zero_flow_price_certificate_sha256
            ),
            "policy": self.policy.to_dict(),
            "passed": self.passed,
            "failed_surface_count": self.failed_surface_count,
            "unresolved_difference_count": self.unresolved_difference_count,
            "cases": [case.to_dict() for case in self.cases],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class SemanticReplayValidator:
    """Validate two complete bundles under the named portable-profile policy."""

    def __init__(
        self,
        *,
        reference_root: Path,
        candidate_root: Path,
        policy: SemanticParityPolicy | None = None,
        bus_price_certificate: BusPriceDegeneracyResult | None = None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None = None,
    ) -> None:
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.policy = policy or SemanticParityPolicy()
        self.bus_price_certificate = bus_price_certificate
        self.zero_flow_price_certificate = zero_flow_price_certificate
        self.comparator = SemanticCaseComparator(self.policy)

    def compare(self, trading_date: str) -> SemanticReplayResult:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        if (
            reference.trading_date != candidate.trading_date
            or reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-SEMANTIC: replay bundle provenance does not match"
            )
        certificate_by_id: dict[str, BusPriceCaseCertificate] = {}
        profile = SEMANTIC_PARITY_PROFILE
        certificate_sha256 = None
        if self.bus_price_certificate is not None:
            certificate = self.bus_price_certificate
            certificate.validate()
            if (
                not certificate.passed
                or certificate.trading_date != trading_date
                or certificate.source_sha256 != reference.source_sha256
                or certificate.reference_bundle_sha256 != reference.logical_sha256
                or certificate.candidate_bundle_sha256 != candidate.logical_sha256
                or tuple(case.case_id for case in certificate.cases)
                != reference.affected_case_ids
            ):
                raise EvidenceContractError(
                    "REQ-G12-SEMANTIC: bus-price certificate provenance does not match"
                )
            certificate_by_id = {case.case_id: case for case in certificate.cases}
            profile = SEMANTIC_CERTIFIED_PARITY_PROFILE
            certificate_sha256 = certificate.logical_sha256
        zero_flow_certificate_sha256 = None
        if self.zero_flow_price_certificate is not None:
            zero_flow = self.zero_flow_price_certificate
            zero_flow.validate()
            if (
                not zero_flow.passed
                or zero_flow.trading_date != trading_date
                or zero_flow.source_sha256 != reference.source_sha256
                or zero_flow.reference_bundle_sha256 != reference.logical_sha256
                or zero_flow.candidate_bundle_sha256 != candidate.logical_sha256
                or tuple(case.case_id for case in zero_flow.cases)
                != reference.affected_case_ids
            ):
                raise EvidenceContractError(
                    "REQ-G12-SEMANTIC: zero-flow certificate provenance does not match"
                )
            profile = SEMANTIC_ZERO_FLOW_CERTIFIED_PARITY_PROFILE
            zero_flow_certificate_sha256 = zero_flow.logical_sha256
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        cases = []
        for expected in reference_cases:
            actual = candidate_by_id[expected.case_id]
            surfaces = {
                surface: self.comparator.compare_surface(
                    surface=surface,
                    reference=expected.surfaces[surface],
                    candidate=actual.surfaces[surface],
                    repaired_reference=expected.surfaces["repaired-bus-price"],
                    repaired_candidate=actual.surfaces["repaired-bus-price"],
                    bus_price_certificate=certificate_by_id.get(expected.case_id),
                    zero_flow_price_certificate=self.zero_flow_price_certificate,
                )
                for surface in sorted(REQUIRED_E2E_SURFACES)
            }
            cases.append(SemanticCaseResult(expected.case_id, surfaces))
        unsigned = {
            "schema_version": 1,
            "profile": profile,
            "trading_date": trading_date,
            "source_sha256": reference.source_sha256,
            "work_item_sha256": reference.work_item_sha256,
            "reference_bundle_sha256": reference.logical_sha256,
            "candidate_bundle_sha256": candidate.logical_sha256,
            "bus_price_certificate_sha256": certificate_sha256,
            "zero_flow_price_certificate_sha256": zero_flow_certificate_sha256,
            "policy": self.policy.to_dict(),
            "passed": bool(cases and all(case.passed for case in cases)),
            "failed_surface_count": sum(
                not surface.passed
                for case in cases
                for surface in case.surfaces.values()
            ),
            "unresolved_difference_count": sum(
                case.unresolved_difference_count for case in cases
            ),
            "cases": [case.to_dict() for case in cases],
        }
        return SemanticReplayResult(
            trading_date=trading_date,
            source_sha256=reference.source_sha256,
            work_item_sha256=reference.work_item_sha256,
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            profile=profile,
            bus_price_certificate_sha256=certificate_sha256,
            zero_flow_price_certificate_sha256=zero_flow_certificate_sha256,
            policy=self.policy,
            cases=tuple(cases),
            logical_sha256=_logical_sha256(unsigned),
        )


class SemanticReplayResultStore:
    """Atomically persist one immutable semantic comparison artifact."""

    def write(self, result: SemanticReplayResult, target: Path) -> Path:
        if result.logical_sha256 != _logical_sha256(result.to_dict(include_hash=False)):
            raise EvidenceContractError(
                "REQ-G12-SEMANTIC: semantic result hash mismatch"
            )
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-SEMANTIC: semantic result already exists"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target
