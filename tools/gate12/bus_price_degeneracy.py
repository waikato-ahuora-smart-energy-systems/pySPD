"""Independent node-allocation certificates for solver-degenerate bus prices."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.reserve.data import RESERVE_FORMULATION_ID, ReserveCase
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore

BUS_PRICE_DEGENERACY_PROFILE = "gams-pyspd-bus-node-nullspace-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
type Key = tuple[str, ...]


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _maximum(values: Mapping[Key, float]) -> float:
    return max((abs(value) for value in values.values()), default=0.0)


def _surface_mapping(payload: bytes, *, surface: str) -> dict[Key, float]:
    try:
        rows = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceContractError(
            f"REQ-G12-BUS-CERT: unreadable {surface} surface"
        ) from error
    if not isinstance(rows, list):
        raise EvidenceContractError(
            f"REQ-G12-BUS-CERT: {surface} surface must be a mapping"
        )
    output: dict[Key, float] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"identity", "value"}:
            raise EvidenceContractError(
                f"REQ-G12-BUS-CERT: invalid {surface} row"
            )
        identity = row["identity"]
        if (
            not isinstance(identity, list)
            or not identity
            or any(not isinstance(item, str) or not item for item in identity)
            or not isinstance(row["value"], str)
        ):
            raise EvidenceContractError(
                f"REQ-G12-BUS-CERT: invalid {surface} identity or value"
            )
        try:
            value = float.fromhex(row["value"])
        except ValueError as error:
            raise EvidenceContractError(
                f"REQ-G12-BUS-CERT: invalid {surface} numeric value"
            ) from error
        key = tuple(identity)
        if key in output or not math.isfinite(value):
            raise EvidenceContractError(
                f"REQ-G12-BUS-CERT: duplicate or non-finite {surface} row"
            )
        output[key] = value
    return output


@dataclass(frozen=True, slots=True)
class BusPriceCaseCertificate:
    """One case's bus-delta projection through the source allocation matrix."""

    case_id: str
    allocation_sha256: str
    bus_count: int
    node_count: int
    allocation_count: int
    normalized_raw_sentinel_count: int
    above_tolerance_raw_bus_count: int
    above_tolerance_repaired_bus_count: int
    maximum_raw_bus_absolute_difference: float
    maximum_repaired_bus_absolute_difference: float
    maximum_raw_projected_node_difference: float
    maximum_repaired_projected_node_difference: float
    maximum_node_absolute_difference: float
    maximum_projection_residual: float
    price_tolerance: float
    projection_tolerance: float

    @classmethod
    def from_dict(cls, payload: object) -> BusPriceCaseCertificate:
        expected = {
            "case_id",
            "passed",
            "allocation_sha256",
            "bus_count",
            "node_count",
            "allocation_count",
            "normalized_raw_sentinel_count",
            "above_tolerance_raw_bus_count",
            "above_tolerance_repaired_bus_count",
            "maximum_raw_bus_absolute_difference",
            "maximum_repaired_bus_absolute_difference",
            "maximum_raw_projected_node_difference",
            "maximum_repaired_projected_node_difference",
            "maximum_node_absolute_difference",
            "maximum_projection_residual",
            "price_tolerance",
            "projection_tolerance",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: unexpected case certificate schema"
            )

        def number(name: str) -> float:
            raw = payload[name]
            if not isinstance(raw, str):
                raise EvidenceContractError(
                    "REQ-G12-BUS-CERT: certificate number must be hexadecimal text"
                )
            try:
                value = float.fromhex(raw)
            except ValueError as error:
                raise EvidenceContractError(
                    "REQ-G12-BUS-CERT: invalid certificate number"
                ) from error
            if not math.isfinite(value) or value < 0.0:
                raise EvidenceContractError(
                    "REQ-G12-BUS-CERT: certificate number is not non-negative"
                )
            return value

        counters = (
            "bus_count",
            "node_count",
            "allocation_count",
            "normalized_raw_sentinel_count",
            "above_tolerance_raw_bus_count",
            "above_tolerance_repaired_bus_count",
        )
        if any(
            not isinstance(payload[name], int)
            or isinstance(payload[name], bool)
            or payload[name] < 0
            for name in counters
        ):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: invalid certificate count"
            )
        case = cls(
            case_id=payload["case_id"],
            allocation_sha256=payload["allocation_sha256"],
            bus_count=payload["bus_count"],
            node_count=payload["node_count"],
            allocation_count=payload["allocation_count"],
            normalized_raw_sentinel_count=payload[
                "normalized_raw_sentinel_count"
            ],
            above_tolerance_raw_bus_count=payload[
                "above_tolerance_raw_bus_count"
            ],
            above_tolerance_repaired_bus_count=payload[
                "above_tolerance_repaired_bus_count"
            ],
            maximum_raw_bus_absolute_difference=number(
                "maximum_raw_bus_absolute_difference"
            ),
            maximum_repaired_bus_absolute_difference=number(
                "maximum_repaired_bus_absolute_difference"
            ),
            maximum_raw_projected_node_difference=number(
                "maximum_raw_projected_node_difference"
            ),
            maximum_repaired_projected_node_difference=number(
                "maximum_repaired_projected_node_difference"
            ),
            maximum_node_absolute_difference=number(
                "maximum_node_absolute_difference"
            ),
            maximum_projection_residual=number("maximum_projection_residual"),
            price_tolerance=number("price_tolerance"),
            projection_tolerance=number("projection_tolerance"),
        )
        if (
            not isinstance(case.case_id, str)
            or not case.case_id
            or not isinstance(case.allocation_sha256, str)
            or not _SHA256.fullmatch(case.allocation_sha256)
            or payload["passed"] is not case.passed
        ):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: invalid case certificate disposition"
            )
        return case

    @property
    def passed(self) -> bool:
        return (
            self.maximum_raw_projected_node_difference <= self.price_tolerance
            and self.maximum_node_absolute_difference <= self.price_tolerance
            and self.maximum_projection_residual <= self.projection_tolerance
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "allocation_sha256": self.allocation_sha256,
            "bus_count": self.bus_count,
            "node_count": self.node_count,
            "allocation_count": self.allocation_count,
            "normalized_raw_sentinel_count": self.normalized_raw_sentinel_count,
            "above_tolerance_raw_bus_count": self.above_tolerance_raw_bus_count,
            "above_tolerance_repaired_bus_count": (
                self.above_tolerance_repaired_bus_count
            ),
            "maximum_raw_bus_absolute_difference": (
                self.maximum_raw_bus_absolute_difference.hex()
            ),
            "maximum_repaired_bus_absolute_difference": (
                self.maximum_repaired_bus_absolute_difference.hex()
            ),
            "maximum_raw_projected_node_difference": (
                self.maximum_raw_projected_node_difference.hex()
            ),
            "maximum_repaired_projected_node_difference": (
                self.maximum_repaired_projected_node_difference.hex()
            ),
            "maximum_node_absolute_difference": (
                self.maximum_node_absolute_difference.hex()
            ),
            "maximum_projection_residual": self.maximum_projection_residual.hex(),
            "price_tolerance": self.price_tolerance.hex(),
            "projection_tolerance": self.projection_tolerance.hex(),
        }


class BusPriceDegeneracyValidator:
    """Prove bus dual deltas are invisible at the canonical node-price layer."""

    def __init__(
        self, *, price_tolerance: float = 1e-4, projection_tolerance: float = 1e-10
    ) -> None:
        if any(
            not math.isfinite(value) or value < 0.0
            for value in (price_tolerance, projection_tolerance)
        ):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: tolerances must be finite and non-negative"
            )
        self.price_tolerance = price_tolerance
        self.projection_tolerance = projection_tolerance

    def compare_case(
        self,
        *,
        case_id: str,
        raw_reference: Mapping[Key, float],
        raw_candidate: Mapping[Key, float],
        repaired_reference: Mapping[Key, float],
        repaired_candidate: Mapping[Key, float],
        node_reference: Mapping[Key, float],
        node_candidate: Mapping[Key, float],
        node_bus_allocation: Mapping[Key, float],
    ) -> BusPriceCaseCertificate:
        raw_keys = set(raw_reference)
        if raw_keys != set(raw_candidate):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: raw bus identities do not match"
            )
        repaired_keys = set(repaired_reference)
        if repaired_keys != set(repaired_candidate) or repaired_keys != raw_keys:
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: repaired bus identities do not match"
            )
        node_keys = set(node_reference)
        if node_keys != set(node_candidate):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: node identities do not match"
            )
        if not raw_keys or not node_keys or not node_bus_allocation:
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: bus, node, and allocation evidence is required"
            )
        if any(
            len(key) != 3 or key[0] != case_id for key in raw_keys | node_keys
        ):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: case-scoped price identity is invalid"
            )

        raw_delta = {
            key: raw_candidate[key] - raw_reference[key] for key in raw_keys
        }
        repaired_delta = {
            key: repaired_candidate[key] - repaired_reference[key]
            for key in repaired_keys
        }
        observed_node_delta = {
            key: node_candidate[key] - node_reference[key] for key in node_keys
        }
        normalized_raw_delta = dict(raw_delta)
        normalized_sentinels = 0
        for key in raw_keys:
            has_sentinel = any(
                abs(value) == 500_000.0
                for value in (raw_reference[key], raw_candidate[key])
            )
            if (
                has_sentinel
                and raw_reference[key] != raw_candidate[key]
                and abs(repaired_delta[key]) <= self.price_tolerance
            ):
                normalized_raw_delta[key] = repaired_delta[key]
                normalized_sentinels += 1
        raw_projection = dict.fromkeys(node_keys, 0.0)
        repaired_projection = dict.fromkeys(node_keys, 0.0)
        allocation_rows = []
        for key, weight in sorted(node_bus_allocation.items()):
            if len(key) != 4 or key[0] != case_id or not math.isfinite(weight):
                raise EvidenceContractError(
                    "REQ-G12-BUS-CERT: allocation identity or weight is invalid"
                )
            node = key[:3]
            bus = key[:2] + (key[3],)
            if node not in node_keys or bus not in raw_keys:
                raise EvidenceContractError(
                    "REQ-G12-BUS-CERT: allocation references an unknown price identity"
                )
            raw_projection[node] += weight * normalized_raw_delta[bus]
            repaired_projection[node] += weight * repaired_delta[bus]
            allocation_rows.append([*key, float(weight).hex()])
        residual = {
            node: repaired_projection[node] - observed_node_delta[node]
            for node in node_keys
        }
        allocation_sha256 = _logical_sha256(allocation_rows)
        return BusPriceCaseCertificate(
            case_id=case_id,
            allocation_sha256=allocation_sha256,
            bus_count=len(raw_keys),
            node_count=len(node_keys),
            allocation_count=len(allocation_rows),
            normalized_raw_sentinel_count=normalized_sentinels,
            above_tolerance_raw_bus_count=sum(
                abs(value) > self.price_tolerance for value in raw_delta.values()
            ),
            above_tolerance_repaired_bus_count=sum(
                abs(value) > self.price_tolerance
                for value in repaired_delta.values()
            ),
            maximum_raw_bus_absolute_difference=_maximum(raw_delta),
            maximum_repaired_bus_absolute_difference=_maximum(repaired_delta),
            maximum_raw_projected_node_difference=_maximum(raw_projection),
            maximum_repaired_projected_node_difference=_maximum(repaired_projection),
            maximum_node_absolute_difference=_maximum(observed_node_delta),
            maximum_projection_residual=_maximum(residual),
            price_tolerance=self.price_tolerance,
            projection_tolerance=self.projection_tolerance,
        )


@dataclass(frozen=True, slots=True)
class BusPriceDegeneracyResult:
    """Hash-bound daily set of case-specific bus-price certificates."""

    trading_date: str
    source_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    cases: tuple[BusPriceCaseCertificate, ...]
    logical_sha256: str

    @classmethod
    def create(
        cls,
        *,
        trading_date: str,
        source_sha256: str,
        reference_bundle_sha256: str,
        candidate_bundle_sha256: str,
        cases: tuple[BusPriceCaseCertificate, ...],
    ) -> BusPriceDegeneracyResult:
        unsigned = {
            "schema_version": 1,
            "profile": BUS_PRICE_DEGENERACY_PROFILE,
            "trading_date": trading_date,
            "source_sha256": source_sha256,
            "reference_bundle_sha256": reference_bundle_sha256,
            "candidate_bundle_sha256": candidate_bundle_sha256,
            "passed": bool(cases and all(case.passed for case in cases)),
            "cases": [case.to_dict() for case in cases],
        }
        result = cls(
            trading_date=trading_date,
            source_sha256=source_sha256,
            reference_bundle_sha256=reference_bundle_sha256,
            candidate_bundle_sha256=candidate_bundle_sha256,
            cases=cases,
            logical_sha256=_logical_sha256(unsigned),
        )
        result.validate()
        return result

    @classmethod
    def from_dict(cls, payload: object) -> BusPriceDegeneracyResult:
        expected = {
            "schema_version",
            "profile",
            "trading_date",
            "source_sha256",
            "reference_bundle_sha256",
            "candidate_bundle_sha256",
            "passed",
            "cases",
            "logical_sha256",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != expected
            or payload.get("schema_version") != 1
            or payload.get("profile") != BUS_PRICE_DEGENERACY_PROFILE
            or not isinstance(payload.get("cases"), list)
        ):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: unexpected certificate result schema"
            )
        result = cls(
            trading_date=payload["trading_date"],
            source_sha256=payload["source_sha256"],
            reference_bundle_sha256=payload["reference_bundle_sha256"],
            candidate_bundle_sha256=payload["candidate_bundle_sha256"],
            cases=tuple(
                BusPriceCaseCertificate.from_dict(item) for item in payload["cases"]
            ),
            logical_sha256=payload["logical_sha256"],
        )
        result.validate()
        if payload["passed"] is not result.passed:
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: certificate result disposition mismatch"
            )
        return result

    @property
    def passed(self) -> bool:
        return bool(self.cases and all(case.passed for case in self.cases))

    def validate(self) -> None:
        if (
            not re.fullmatch(r"[0-9]{8}", self.trading_date)
            or any(
                not _SHA256.fullmatch(value)
                for value in (
                    self.source_sha256,
                    self.reference_bundle_sha256,
                    self.candidate_bundle_sha256,
                    self.logical_sha256,
                )
            )
            or not self.cases
            or len({case.case_id for case in self.cases}) != len(self.cases)
            or self.logical_sha256 != _logical_sha256(self.to_dict(include_hash=False))
        ):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: invalid certificate result"
            )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": BUS_PRICE_DEGENERACY_PROFILE,
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "passed": self.passed,
            "cases": [case.to_dict() for case in self.cases],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class BusPriceDegeneracyRunner:
    """Load the source allocation matrix and certify two canonical bundles."""

    def __init__(
        self,
        *,
        input_path: Path,
        system_directory: Path,
        reference_root: Path,
        candidate_root: Path,
    ) -> None:
        self.input_path = input_path
        self.system_directory = system_directory
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.validator = BusPriceDegeneracyValidator()

    def run(self, trading_date: str) -> BusPriceDegeneracyResult:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        if (
            reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: replay bundle provenance does not match"
            )
        configuration = ApplicationConfiguration(
            formulation_id=RESERVE_FORMULATION_ID,
            input_path=self.input_path,
            output_directory=self.input_path.parent / ".bus-price-certificate",
            source_sha256=reference.source_sha256,
            gams_system_directory=self.system_directory,
            case_ids=reference.affected_case_ids,
        )
        reference_by_id = {case.case_id: case for case in reference_cases}
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        certificates = []
        for prepared in PyspdApplication().iter_prepared_cases(configuration):
            case_id = prepared.specification.case_id
            payload = prepared.payload
            if not isinstance(payload, ReserveCase) or payload.network is None:
                raise EvidenceContractError(
                    "REQ-G12-BUS-CERT: source case has no v5 allocation matrix"
                )
            expected = reference_by_id[case_id]
            actual = candidate_by_id[case_id]
            certificates.append(
                self.validator.compare_case(
                    case_id=case_id,
                    raw_reference=_surface_mapping(
                        expected.surfaces["raw-bus-price"], surface="raw-bus-price"
                    ),
                    raw_candidate=_surface_mapping(
                        actual.surfaces["raw-bus-price"], surface="raw-bus-price"
                    ),
                    repaired_reference=_surface_mapping(
                        expected.surfaces["repaired-bus-price"],
                        surface="repaired-bus-price",
                    ),
                    repaired_candidate=_surface_mapping(
                        actual.surfaces["repaired-bus-price"],
                        surface="repaired-bus-price",
                    ),
                    node_reference=_surface_mapping(
                        expected.surfaces["node-price"], surface="node-price"
                    ),
                    node_candidate=_surface_mapping(
                        actual.surfaces["node-price"], surface="node-price"
                    ),
                    node_bus_allocation=payload.network.node_bus_allocation,
                )
            )
        if tuple(case.case_id for case in certificates) != reference.affected_case_ids:
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: prepared case order is incomplete"
            )
        return BusPriceDegeneracyResult.create(
            trading_date=trading_date,
            source_sha256=reference.source_sha256,
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            cases=tuple(certificates),
        )


class BusPriceDegeneracyResultStore:
    """Atomically persist one immutable daily bus-price certificate."""

    def write(self, result: BusPriceDegeneracyResult, target: Path) -> Path:
        result.validate()
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: certificate output already exists"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def load(self, path: Path) -> BusPriceDegeneracyResult:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-BUS-CERT: unreadable certificate result"
            ) from error
        return BusPriceDegeneracyResult.from_dict(payload)
