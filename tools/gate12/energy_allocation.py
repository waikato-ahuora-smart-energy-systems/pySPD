"""Hash-bound certificates for source-proven equivalent energy allocations."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from tools.gate12.evidence import EvidenceContractError

ENERGY_ALLOCATION_PROFILE = "gams-pyspd-lossless-equal-price-allocation-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CERTIFIABLE_OBSERVABLES = frozenset(
    {"generation-mw", "bus-generation", "branch-flow-mw", "node-generation"}
)
type Key = tuple[str, ...]


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class EnergyAllocationCertificate:
    """One immutable proof boundary for an economically equivalent allocation."""

    source_sha256: str
    benchmark_sha256: str
    records_sha256: str
    reference_sha256: dict[str, str]
    case_id: str
    date_time: str
    marginal_block_price: float
    transferred_mw: float
    accepted_identities: frozenset[Key]
    logical_sha256: str
    profile: str = ENERGY_ALLOCATION_PROFILE

    @property
    def passed(self) -> bool:
        return bool(self.accepted_identities)

    def certifies(self, identity: Key) -> bool:
        return identity in self.accepted_identities

    def validate(self) -> None:
        hashes = (
            self.source_sha256,
            self.benchmark_sha256,
            self.records_sha256,
            self.logical_sha256,
            *self.reference_sha256.values(),
        )
        if (
            self.profile != ENERGY_ALLOCATION_PROFILE
            or not self.case_id
            or not self.date_time
            or any(not _SHA256.fullmatch(value) for value in hashes)
            or not math.isfinite(self.marginal_block_price)
            or not math.isfinite(self.transferred_mw)
            or self.transferred_mw <= 0.0
            or not self.passed
            or any(
                len(identity) < 2
                or identity[-1] not in _CERTIFIABLE_OBSERVABLES
                or any(not item for item in identity)
                for identity in self.accepted_identities
            )
        ):
            raise EvidenceContractError(
                "REQ-G12-ENERGY-ALLOCATION: invalid certificate"
            )
        if self.logical_sha256 != _logical_sha256(self.to_dict(include_hash=False)):
            raise EvidenceContractError(
                "REQ-G12-ENERGY-ALLOCATION: certificate hash mismatch"
            )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": self.profile,
            "scope": "source-proven-lossless-equal-price-allocation-identities",
            "passed": self.passed,
            "source_sha256": self.source_sha256,
            "benchmark_sha256": self.benchmark_sha256,
            "records_sha256": self.records_sha256,
            "reference_sha256": dict(sorted(self.reference_sha256.items())),
            "case_id": self.case_id,
            "date_time": self.date_time,
            "marginal_block_price": self.marginal_block_price.hex(),
            "transferred_mw": self.transferred_mw.hex(),
            "accepted_identities": [
                list(identity) for identity in sorted(self.accepted_identities)
            ],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> EnergyAllocationCertificate:
        expected = {
            "schema_version",
            "profile",
            "scope",
            "passed",
            "source_sha256",
            "benchmark_sha256",
            "records_sha256",
            "reference_sha256",
            "case_id",
            "date_time",
            "marginal_block_price",
            "transferred_mw",
            "accepted_identities",
            "logical_sha256",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise EvidenceContractError(
                "REQ-G12-ENERGY-ALLOCATION: unexpected certificate schema"
            )
        if (
            payload["schema_version"] != 1
            or payload["profile"] != ENERGY_ALLOCATION_PROFILE
            or payload["scope"]
            != "source-proven-lossless-equal-price-allocation-identities"
            or payload["passed"] is not True
            or not isinstance(payload["reference_sha256"], dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in payload["reference_sha256"].items()
            )
            or not isinstance(payload["accepted_identities"], list)
        ):
            raise EvidenceContractError(
                "REQ-G12-ENERGY-ALLOCATION: malformed certificate"
            )
        try:
            price = float.fromhex(payload["marginal_block_price"])
            transferred = float.fromhex(payload["transferred_mw"])
        except (TypeError, ValueError) as error:
            raise EvidenceContractError(
                "REQ-G12-ENERGY-ALLOCATION: invalid numeric evidence"
            ) from error
        identities: set[Key] = set()
        for raw in payload["accepted_identities"]:
            if (
                not isinstance(raw, list)
                or not raw
                or any(not isinstance(item, str) or not item for item in raw)
            ):
                raise EvidenceContractError(
                    "REQ-G12-ENERGY-ALLOCATION: invalid accepted identity"
                )
            identity = tuple(raw)
            if identity in identities:
                raise EvidenceContractError(
                    "REQ-G12-ENERGY-ALLOCATION: duplicate accepted identity"
                )
            identities.add(identity)
        certificate = cls(
            source_sha256=payload["source_sha256"],
            benchmark_sha256=payload["benchmark_sha256"],
            records_sha256=payload["records_sha256"],
            reference_sha256=dict(payload["reference_sha256"]),
            case_id=payload["case_id"],
            date_time=payload["date_time"],
            marginal_block_price=price,
            transferred_mw=transferred,
            accepted_identities=frozenset(identities),
            logical_sha256=payload["logical_sha256"],
            profile=payload["profile"],
        )
        certificate.validate()
        return certificate


class EnergyAllocationCertificateStore:
    """Load a certificate without permitting schema or hash drift."""

    def load(self, source: Path) -> EnergyAllocationCertificate:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-ENERGY-ALLOCATION: unreadable certificate"
            ) from error
        return EnergyAllocationCertificate.from_dict(payload)
