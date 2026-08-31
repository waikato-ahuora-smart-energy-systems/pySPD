"""Quantified, hash-bound differences between canonical Gate 12 bundles."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore

_MISSING = object()
_HEX_NUMBER = re.compile(r"[+-]?0x[0-9a-f]+(?:\.[0-9a-f]*)?p[+-]?[0-9]+", re.IGNORECASE)
_DECIMAL_NUMBER = re.compile(
    r"[+-]?(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|"
    r"[0-9]+[eE][+-]?[0-9]+)"
)


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalValueDifference:
    """One leaf-level structural or value difference."""

    path: tuple[str, ...]
    kind: str
    reference: object | None
    candidate: object | None
    absolute_error: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": list(self.path),
            "kind": self.kind,
            "reference": self.reference,
            "candidate": self.candidate,
            "absolute_error": (
                None if self.absolute_error is None else self.absolute_error.hex()
            ),
        }


@dataclass(frozen=True, slots=True)
class CanonicalJsonDifference:
    """Complete path-level comparison of two canonical JSON documents."""

    reference_sha256: str
    candidate_sha256: str
    reference_leaf_count: int
    candidate_leaf_count: int
    missing_path_count: int
    extra_path_count: int
    changed_value_count: int
    numeric_difference_count: int
    maximum_absolute_error: float
    differences: tuple[CanonicalValueDifference, ...]

    @property
    def identical(self) -> bool:
        return self.reference_sha256 == self.candidate_sha256 and not self.differences

    @property
    def unresolved_difference_count(self) -> int:
        return len(self.differences)

    def to_dict(self) -> dict[str, object]:
        return {
            "identical": self.identical,
            "reference_sha256": self.reference_sha256,
            "candidate_sha256": self.candidate_sha256,
            "reference_leaf_count": self.reference_leaf_count,
            "candidate_leaf_count": self.candidate_leaf_count,
            "missing_path_count": self.missing_path_count,
            "extra_path_count": self.extra_path_count,
            "changed_value_count": self.changed_value_count,
            "numeric_difference_count": self.numeric_difference_count,
            "maximum_absolute_error": self.maximum_absolute_error.hex(),
            "unresolved_difference_count": self.unresolved_difference_count,
            "differences": [difference.to_dict() for difference in self.differences],
        }


class CanonicalJsonDiffer:
    """Compare canonical JSON without collapsing identity or numeric magnitude."""

    def compare(self, reference: bytes, candidate: bytes) -> CanonicalJsonDifference:
        reference_payload = self._load(reference, side="reference")
        candidate_payload = self._load(candidate, side="candidate")
        reference_leaves = self._flatten(reference_payload)
        candidate_leaves = self._flatten(candidate_payload)
        differences: list[CanonicalValueDifference] = []
        missing = 0
        extra = 0
        changed = 0
        numeric = 0
        maximum_error = 0.0
        for path in sorted(set(reference_leaves) | set(candidate_leaves)):
            expected = reference_leaves.get(path, _MISSING)
            actual = candidate_leaves.get(path, _MISSING)
            if expected is _MISSING:
                extra += 1
                differences.append(
                    CanonicalValueDifference(path, "extra", None, actual, None)
                )
                continue
            if actual is _MISSING:
                missing += 1
                differences.append(
                    CanonicalValueDifference(path, "missing", expected, None, None)
                )
                continue
            if expected == actual and type(expected) is type(actual):
                continue
            error = self._absolute_error(expected, actual)
            if error is not None:
                numeric += 1
                maximum_error = max(maximum_error, error)
            changed += 1
            differences.append(
                CanonicalValueDifference(path, "changed", expected, actual, error)
            )
        reference_sha256 = hashlib.sha256(reference).hexdigest()
        candidate_sha256 = hashlib.sha256(candidate).hexdigest()
        if not differences and reference_sha256 != candidate_sha256:
            differences.append(
                CanonicalValueDifference(
                    (), "encoding", reference_sha256, candidate_sha256, None
                )
            )
        return CanonicalJsonDifference(
            reference_sha256=reference_sha256,
            candidate_sha256=candidate_sha256,
            reference_leaf_count=len(reference_leaves),
            candidate_leaf_count=len(candidate_leaves),
            missing_path_count=missing,
            extra_path_count=extra,
            changed_value_count=changed,
            numeric_difference_count=numeric,
            maximum_absolute_error=maximum_error,
            differences=tuple(differences),
        )

    @staticmethod
    def _load(payload: bytes, *, side: str) -> object:
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                f"REQ-G12-DIFF: {side} canonical JSON is unreadable"
            ) from error
        return value

    def _flatten(
        self, payload: object, path: tuple[str, ...] = ()
    ) -> dict[tuple[str, ...], object]:
        if isinstance(payload, dict) and payload:
            output: dict[tuple[str, ...], object] = {}
            for key in sorted(payload):
                if not isinstance(key, str):
                    raise EvidenceContractError(
                        "REQ-G12-DIFF: canonical JSON object key must be text"
                    )
                output.update(self._flatten(payload[key], (*path, key)))
            return output
        if isinstance(payload, list) and payload:
            identity_rows = self._identity_rows(payload)
            if identity_rows is not None:
                output = {}
                for identity, row in sorted(identity_rows.items()):
                    for key in sorted(row):
                        if key != "identity":
                            output.update(
                                self._flatten(
                                    row[key],
                                    (*path, f"identity={identity}", key),
                                )
                            )
                return output
            output = {}
            for index, value in enumerate(payload):
                output.update(self._flatten(value, (*path, str(index))))
            return output
        if isinstance(payload, float) and not math.isfinite(payload):
            raise EvidenceContractError(
                "REQ-G12-DIFF: canonical JSON contains a non-finite number"
            )
        return {path: payload}

    @staticmethod
    def _identity_rows(payload: list[object]) -> dict[str, dict[str, object]] | None:
        if not all(
            isinstance(row, dict)
            and isinstance(row.get("identity"), list)
            and all(isinstance(item, str) for item in row["identity"])
            for row in payload
        ):
            return None
        rows: dict[str, dict[str, object]] = {}
        for raw_row in payload:
            assert isinstance(raw_row, dict)
            row = {str(key): value for key, value in raw_row.items()}
            identity = json.dumps(row["identity"], separators=(",", ":"))
            if identity in rows:
                raise EvidenceContractError(
                    "REQ-G12-DIFF: canonical mapping contains duplicate identity"
                )
            rows[identity] = row
        return rows

    @staticmethod
    def _absolute_error(reference: object, candidate: object) -> float | None:
        expected = CanonicalJsonDiffer._number(reference)
        actual = CanonicalJsonDiffer._number(candidate)
        if expected is None or actual is None:
            return None
        return abs(expected - actual)

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            try:
                if _HEX_NUMBER.fullmatch(value):
                    number = float.fromhex(value)
                elif _DECIMAL_NUMBER.fullmatch(value):
                    number = float(value)
                else:
                    return None
            except ValueError:
                return None
        else:
            return None
        if not math.isfinite(number):
            raise EvidenceContractError(
                "REQ-G12-DIFF: canonical JSON contains a non-finite number"
            )
        return number


@dataclass(frozen=True, slots=True)
class CanonicalCaseDifference:
    """All twelve canonical surface comparisons for one affected case."""

    case_id: str
    surfaces: dict[str, CanonicalJsonDifference]

    @property
    def changed_surface_count(self) -> int:
        return sum(not surface.identical for surface in self.surfaces.values())

    @property
    def unresolved_difference_count(self) -> int:
        return sum(
            surface.unresolved_difference_count for surface in self.surfaces.values()
        )

    @property
    def maximum_absolute_error(self) -> float:
        return max(
            (surface.maximum_absolute_error for surface in self.surfaces.values()),
            default=0.0,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "changed_surface_count": self.changed_surface_count,
            "unresolved_difference_count": self.unresolved_difference_count,
            "maximum_absolute_error": self.maximum_absolute_error.hex(),
            "surfaces": {
                name: difference.to_dict()
                for name, difference in sorted(self.surfaces.items())
            },
        }


@dataclass(frozen=True, slots=True)
class CanonicalBundleDifference:
    """Hash-bound quantified comparison of two complete daily bundles."""

    trading_date: str
    source_sha256: str
    work_item_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    cases: tuple[CanonicalCaseDifference, ...]
    logical_sha256: str

    @property
    def identical(self) -> bool:
        return bool(self.cases and self.changed_surface_count == 0)

    @property
    def changed_surface_count(self) -> int:
        return sum(case.changed_surface_count for case in self.cases)

    @property
    def unresolved_difference_count(self) -> int:
        return sum(case.unresolved_difference_count for case in self.cases)

    @property
    def maximum_absolute_error(self) -> float:
        return max((case.maximum_absolute_error for case in self.cases), default=0.0)

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": "gams-pyspd-canonical-json-quantified-diff-v1",
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "work_item_sha256": self.work_item_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "identical": self.identical,
            "changed_surface_count": self.changed_surface_count,
            "unresolved_difference_count": self.unresolved_difference_count,
            "maximum_absolute_error": self.maximum_absolute_error.hex(),
            "cases": [case.to_dict() for case in self.cases],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class CanonicalBundleDifferenceStore:
    """Atomically persist one immutable quantified daily comparison."""

    def write(self, difference: CanonicalBundleDifference, target: Path) -> Path:
        if difference.logical_sha256 != _logical_sha256(
            difference.to_dict(include_hash=False)
        ):
            raise EvidenceContractError(
                "REQ-G12-DIFF: quantified difference hash mismatch"
            )
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError(
                "REQ-G12-DIFF: quantified difference output already exists"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(difference.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target


class CanonicalBundleDiffer:
    """Load, verify, and quantify two same-provenance replay bundles."""

    def __init__(self, *, reference_root: Path, candidate_root: Path) -> None:
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.json_differ = CanonicalJsonDiffer()

    def compare(self, trading_date: str) -> CanonicalBundleDifference:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        if (
            reference.trading_date != candidate.trading_date
            or reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
        ):
            raise EvidenceContractError(
                "REQ-G12-DIFF: replay bundle provenance does not match"
            )
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        cases = tuple(
            CanonicalCaseDifference(
                case_id=expected.case_id,
                surfaces={
                    surface: self.json_differ.compare(
                        expected.surfaces[surface],
                        candidate_by_id[expected.case_id].surfaces[surface],
                    )
                    for surface in sorted(REQUIRED_E2E_SURFACES)
                },
            )
            for expected in reference_cases
        )
        unsigned = {
            "schema_version": 1,
            "profile": "gams-pyspd-canonical-json-quantified-diff-v1",
            "trading_date": trading_date,
            "source_sha256": reference.source_sha256,
            "work_item_sha256": reference.work_item_sha256,
            "reference_bundle_sha256": reference.logical_sha256,
            "candidate_bundle_sha256": candidate.logical_sha256,
            "identical": bool(
                cases and not any(case.changed_surface_count for case in cases)
            ),
            "changed_surface_count": sum(case.changed_surface_count for case in cases),
            "unresolved_difference_count": sum(
                case.unresolved_difference_count for case in cases
            ),
            "maximum_absolute_error": max(
                (case.maximum_absolute_error for case in cases), default=0.0
            ).hex(),
            "cases": [case.to_dict() for case in cases],
        }
        return CanonicalBundleDifference(
            trading_date=trading_date,
            source_sha256=reference.source_sha256,
            work_item_sha256=reference.work_item_sha256,
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            cases=cases,
            logical_sha256=_logical_sha256(unsigned),
        )
