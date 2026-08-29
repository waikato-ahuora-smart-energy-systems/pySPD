"""Hash-bound and fail-closed release-manifest contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


class DistributionStatus(str, Enum):
    HELD = "held"
    PERMITTED = "permitted"


_LEGAL_STATUSES = frozenset(
    {"pending", "approved", "approved-with-controls", "rejected"}
)


@dataclass(frozen=True, slots=True)
class LegalDecision:
    decision_id: str
    status: str

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("legal decision id must not be empty")
        if self.status not in _LEGAL_STATUSES:
            raise ValueError(f"unsupported legal decision status: {self.status}")


@dataclass(frozen=True, slots=True)
class ReleaseArtifact:
    name: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        if not self.name.strip() or not _valid_sha256(self.sha256) or self.size < 0:
            raise ValueError("invalid release artifact")


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    version: str
    formulation_ids: tuple[str, ...]
    artifacts: tuple[ReleaseArtifact, ...]
    sbom: ReleaseArtifact
    evidence_sha256: str
    legal_decisions: tuple[LegalDecision, ...]
    distribution_status: DistributionStatus
    logical_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "formulation_ids", tuple(self.formulation_ids))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "legal_decisions", tuple(self.legal_decisions))
        if not self.version.strip() or not self.formulation_ids:
            raise ValueError("release version and formulations must not be empty")
        if not _valid_sha256(self.evidence_sha256):
            raise ValueError("evidence_sha256 must be a lowercase SHA-256")
        if not _valid_sha256(self.logical_sha256):
            raise ValueError("logical_sha256 must be a lowercase SHA-256")

    def _logical_dict(self) -> dict[str, object]:
        return {
            "artifacts": [
                {"name": item.name, "sha256": item.sha256, "size": item.size}
                for item in self.artifacts
            ],
            "distribution_status": self.distribution_status.value,
            "evidence_sha256": self.evidence_sha256,
            "formulation_ids": list(self.formulation_ids),
            "legal_decisions": [
                {"decision_id": item.decision_id, "status": item.status}
                for item in self.legal_decisions
            ],
            "sbom": {
                "name": self.sbom.name,
                "sha256": self.sbom.sha256,
                "size": self.sbom.size,
            },
            "schema_version": 1,
            "version": self.version,
        }

    def write(self, path: Path) -> None:
        path.write_bytes(
            _json_bytes({**self._logical_dict(), "logical_sha256": self.logical_sha256})
        )

    @classmethod
    def read(cls, path: Path) -> ReleaseManifest:
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot read release manifest: {error}") from error
        logical_sha256 = str(payload.pop("logical_sha256", ""))
        if _sha256(_json_bytes(payload)) != logical_sha256:
            raise ValueError("release manifest logical hash mismatch")
        try:
            artifacts = tuple(ReleaseArtifact(**item) for item in payload["artifacts"])
            sbom = ReleaseArtifact(**payload["sbom"])
            decisions = tuple(
                LegalDecision(**item) for item in payload["legal_decisions"]
            )
            return cls(
                version=str(payload["version"]),
                formulation_ids=tuple(payload["formulation_ids"]),
                artifacts=artifacts,
                sbom=sbom,
                evidence_sha256=str(payload["evidence_sha256"]),
                legal_decisions=decisions,
                distribution_status=DistributionStatus(payload["distribution_status"]),
                logical_sha256=logical_sha256,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid release manifest: {error}") from error


class ReleaseManifestBuilder:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _artifact(self, path: Path) -> ReleaseArtifact:
        resolved = path.resolve()
        if not resolved.is_file():
            raise ValueError(f"missing release artifact: {path}")
        try:
            name = str(resolved.relative_to(self.root))
        except ValueError as error:
            raise ValueError(f"artifact is outside release root: {path}") from error
        return ReleaseArtifact(name, _file_sha256(resolved), resolved.stat().st_size)

    def build(
        self,
        *,
        version: str,
        formulation_ids: tuple[str, ...],
        artifacts: tuple[Path, ...],
        sbom: Path,
        evidence_sha256: str,
        legal_decisions: tuple[LegalDecision, ...],
    ) -> ReleaseManifest:
        if not _valid_sha256(evidence_sha256):
            raise ValueError("evidence_sha256 must be a lowercase SHA-256")
        packaged = tuple(self._artifact(path) for path in artifacts)
        packaged_sbom = self._artifact(sbom)
        permitted = bool(legal_decisions) and all(
            decision.status in {"approved", "approved-with-controls"}
            for decision in legal_decisions
        )
        logical = {
            "artifacts": [
                {"name": item.name, "sha256": item.sha256, "size": item.size}
                for item in packaged
            ],
            "distribution_status": (
                DistributionStatus.PERMITTED.value
                if permitted
                else DistributionStatus.HELD.value
            ),
            "evidence_sha256": evidence_sha256,
            "formulation_ids": list(formulation_ids),
            "legal_decisions": [
                {"decision_id": item.decision_id, "status": item.status}
                for item in legal_decisions
            ],
            "sbom": {
                "name": packaged_sbom.name,
                "sha256": packaged_sbom.sha256,
                "size": packaged_sbom.size,
            },
            "schema_version": 1,
            "version": version,
        }
        return ReleaseManifest(
            version,
            formulation_ids,
            packaged,
            packaged_sbom,
            evidence_sha256,
            legal_decisions,
            DistributionStatus.PERMITTED if permitted else DistributionStatus.HELD,
            _sha256(_json_bytes(logical)),
        )
