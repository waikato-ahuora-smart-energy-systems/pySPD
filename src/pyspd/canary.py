"""Fail-closed continuous-validation canaries for release evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from pyspd.reporting import ReportManifest


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class CanaryBaseline:
    """An immutable, independently stored expected report signature."""

    formulation_id: str
    report_manifest_sha256: str
    report_files: Mapping[str, str]
    source_sha256: str

    def __post_init__(self) -> None:
        if not self.formulation_id.strip():
            raise ValueError("formulation_id must not be empty")
        _validate_sha256("report_manifest_sha256", self.report_manifest_sha256)
        _validate_sha256("source_sha256", self.source_sha256)
        files = dict(sorted(self.report_files.items()))
        if not files:
            raise ValueError("report_files must not be empty")
        for name, digest in files.items():
            if not name.strip():
                raise ValueError("report filename must not be empty")
            _validate_sha256(f"report_files[{name!r}]", digest)
        object.__setattr__(self, "report_files", MappingProxyType(files))

    def to_dict(self) -> dict[str, object]:
        return {
            "formulation_id": self.formulation_id,
            "report_files": dict(self.report_files),
            "report_manifest_sha256": self.report_manifest_sha256,
            "source_sha256": self.source_sha256,
        }

    @property
    def logical_sha256(self) -> str:
        return _sha256(_json_bytes(self.to_dict()))


class CanaryStatus(str, Enum):
    PASS = "pass"
    QUARANTINED = "quarantined"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class CanaryResult:
    status: CanaryStatus
    baseline_sha256: str
    candidate_sha256: str
    discrepancies: tuple[str, ...]

    @property
    def event_id(self) -> str:
        payload = {
            "baseline_sha256": self.baseline_sha256,
            "candidate_sha256": self.candidate_sha256,
            "discrepancies": list(self.discrepancies),
            "status": self.status.value,
        }
        return _sha256(_json_bytes(payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_sha256": self.baseline_sha256,
            "candidate_sha256": self.candidate_sha256,
            "discrepancies": list(self.discrepancies),
            "event_id": self.event_id,
            "status": self.status.value,
        }


class ContinuousValidationCanary:
    """Compare a candidate report manifest without updating its baseline."""

    def evaluate(
        self, baseline: CanaryBaseline, candidate: ReportManifest
    ) -> CanaryResult:
        if candidate.formulation_id != baseline.formulation_id:
            formulation_discrepancy = (
                f"formulation mismatch: {candidate.formulation_id} != "
                f"{baseline.formulation_id}"
            )
            return CanaryResult(
                CanaryStatus.UNSUPPORTED,
                baseline.logical_sha256,
                candidate.logical_sha256,
                (formulation_discrepancy,),
            )

        discrepancies: list[str] = []
        if candidate.logical_sha256 != baseline.report_manifest_sha256:
            discrepancies.append("report manifest hash mismatch")
        all_files = sorted(set(baseline.report_files) | set(candidate.files))
        for name in all_files:
            expected = baseline.report_files.get(name)
            actual = candidate.files.get(name)
            if expected is None:
                discrepancies.append(f"{name} unexpected")
            elif actual is None:
                discrepancies.append(f"{name} missing")
            elif actual != expected:
                discrepancies.append(f"{name} hash mismatch")
        status = CanaryStatus.QUARANTINED if discrepancies else CanaryStatus.PASS
        return CanaryResult(
            status,
            baseline.logical_sha256,
            candidate.logical_sha256,
            tuple(discrepancies),
        )


class QuarantineStore:
    """Append-only storage for failed or unsupported canary events."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def record(self, result: CanaryResult) -> Path:
        if result.status is CanaryStatus.PASS:
            raise ValueError("passing canary results must not be quarantined")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{result.event_id}.json"
        with path.open("xb") as stream:
            stream.write(_json_bytes(result.to_dict()))
        return path
