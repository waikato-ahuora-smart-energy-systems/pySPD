"""Prefix-complete replay planning for the exact Gate 12 affected population."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, ClassVar

from tools.gate12.evidence import (
    AffectedIntervalIdentity,
    AffectedIntervalManifest,
    EvidenceContractError,
)
from tools.gate12.historical_population import (
    HISTORICAL_EXECUTION_PROFILE,
    HistoricalGdxCaseIndex,
    HistoricalInputInventory,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_TRADING_DATE = re.compile(r"[0-9]{8}")


class HistoricalAffectedManifestLoader:
    """Load only the exact manifest schema emitted by Gate 12 enumeration."""

    _required: ClassVar[frozenset[str]] = frozenset({
        "schema_version",
        "source_release",
        "reference_commit",
        "execution_profile",
        "identities",
    })
    _identity_fields: ClassVar[frozenset[str]] = frozenset({
        "case_id",
        "date_time",
        "trading_period",
        "trading_date",
        "source_sha256",
        "discovery_rationale",
    })

    def from_dict(self, payload: dict[str, Any]) -> AffectedIntervalManifest:
        if (
            set(payload) != self._required
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("source_release"), str)
            or not isinstance(payload.get("reference_commit"), str)
            or not isinstance(payload.get("identities"), list)
        ):
            raise EvidenceContractError(
                "REQ-G12-REPLAY: unexpected affected manifest schema"
            )
        if payload["execution_profile"] != HISTORICAL_EXECUTION_PROFILE:
            raise EvidenceContractError(
                "REQ-G12-REPLAY: affected manifest execution profile mismatch"
            )
        raw_identities = payload["identities"]
        if any(
            not isinstance(item, dict) or set(item) != self._identity_fields
            for item in raw_identities
        ):
            raise EvidenceContractError(
                "REQ-G12-REPLAY: unexpected affected manifest identity schema"
            )
        try:
            identities = tuple(
                AffectedIntervalIdentity(**item) for item in raw_identities
            )
        except TypeError as error:
            raise EvidenceContractError(
                "REQ-G12-REPLAY: invalid affected manifest identity"
            ) from error
        return AffectedIntervalManifest(
            source_release=payload["source_release"],
            reference_commit=payload["reference_commit"],
            identities=identities,
        )


@dataclass(frozen=True)
class HistoricalAffectedReplayBatch:
    """One date's canonical prefix through its last affected interval."""

    trading_date: str
    source_sha256: str
    case_ids: tuple[str, ...]
    affected_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _TRADING_DATE.fullmatch(self.trading_date):
            raise EvidenceContractError("REQ-G12-REPLAY: invalid trading date")
        if not _SHA256.fullmatch(self.source_sha256):
            raise EvidenceContractError("REQ-G12-REPLAY: invalid source hash")
        if (
            not self.case_ids
            or not self.affected_case_ids
            or len(set(self.case_ids)) != len(self.case_ids)
            or len(set(self.affected_case_ids)) != len(self.affected_case_ids)
            or not set(self.affected_case_ids).issubset(self.case_ids)
        ):
            raise EvidenceContractError(
                "REQ-G12-REPLAY: invalid prefix or affected case identities"
            )


@dataclass(frozen=True)
class HistoricalAffectedReplayPlan:
    """Hash-addressed collection of all prefix-complete affected-day replays."""

    batches: tuple[HistoricalAffectedReplayBatch, ...]
    logical_sha256: str

    @property
    def affected_case_count(self) -> int:
        return sum(len(batch.affected_case_ids) for batch in self.batches)

    @property
    def selected_case_count(self) -> int:
        return sum(len(batch.case_ids) for batch in self.batches)

    def to_dict(self) -> dict[str, object]:
        return {
            **self._unsigned_payload(self.batches),
            "affected_case_count": self.affected_case_count,
            "selected_case_count": self.selected_case_count,
            "logical_sha256": self.logical_sha256,
        }

    @staticmethod
    def _unsigned_payload(
        batches: tuple[HistoricalAffectedReplayBatch, ...],
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "policy": "canonical-same-day-prefix-through-last-affected-case",
            "batches": [
                {
                    "trading_date": batch.trading_date,
                    "source_sha256": batch.source_sha256,
                    "case_ids": list(batch.case_ids),
                    "affected_case_ids": list(batch.affected_case_ids),
                }
                for batch in batches
            ],
        }


class HistoricalAffectedReplayPlanner:
    """Preserve all same-day predecessor state needed by affected intervals."""

    def plan(
        self,
        *,
        manifest: AffectedIntervalManifest,
        inventory: HistoricalInputInventory,
        case_indices: dict[str, HistoricalGdxCaseIndex],
    ) -> HistoricalAffectedReplayPlan:
        expected_hashes = {
            artifact.trading_date: artifact.sha256
            for artifact in inventory.artifacts
        }
        manifest.validate(expected_source_hashes=expected_hashes)
        if set(case_indices) != set(expected_hashes):
            raise EvidenceContractError(
                "REQ-G12-REPLAY: GDX indices must cover the exact inventory"
            )
        identities_by_date: dict[str, list[AffectedIntervalIdentity]] = {
            trading_date: [] for trading_date in expected_hashes
        }
        case_ids = [identity.case_id for identity in manifest.identities]
        if len(case_ids) != len(set(case_ids)):
            raise EvidenceContractError(
                "REQ-G12-REPLAY: affected case IDs must be globally unique"
            )
        for identity in manifest.identities:
            identities_by_date[identity.trading_date].append(identity)

        batches = tuple(
            self._batch(
                trading_date=artifact.trading_date,
                source_sha256=artifact.sha256,
                identities=tuple(identities_by_date[artifact.trading_date]),
                index=case_indices[artifact.trading_date],
            )
            for artifact in inventory.artifacts
        )
        payload = HistoricalAffectedReplayPlan._unsigned_payload(batches)
        logical_sha256 = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return HistoricalAffectedReplayPlan(batches, logical_sha256)

    @staticmethod
    def _batch(
        *,
        trading_date: str,
        source_sha256: str,
        identities: tuple[AffectedIntervalIdentity, ...],
        index: HistoricalGdxCaseIndex,
    ) -> HistoricalAffectedReplayBatch:
        position = {identity: offset for offset, identity in enumerate(index.cases)}
        affected_positions: list[tuple[int, AffectedIntervalIdentity]] = []
        for identity in identities:
            key = (identity.case_id, identity.date_time)
            if key not in position:
                raise EvidenceContractError(
                    "REQ-G12-REPLAY: affected identity is absent from canonical GDX "
                    f"index for {trading_date}"
                )
            if index.trading_periods[key] != identity.trading_period:
                raise EvidenceContractError(
                    "REQ-G12-REPLAY: affected identity trading period mismatch"
                )
            affected_positions.append((position[key], identity))
        if not affected_positions:
            raise EvidenceContractError(
                "REQ-G12-REPLAY: every governed date needs an affected identity"
            )
        affected_positions.sort(key=lambda item: item[0])
        last_position = affected_positions[-1][0]
        prefix = index.cases[: last_position + 1]
        prefix_case_ids = tuple(case_id for case_id, _ in prefix)
        if len(prefix_case_ids) != len(set(prefix_case_ids)):
            raise EvidenceContractError(
                "REQ-G12-REPLAY: canonical GDX prefix contains duplicate case IDs"
            )
        return HistoricalAffectedReplayBatch(
            trading_date=trading_date,
            source_sha256=source_sha256,
            case_ids=prefix_case_ids,
            affected_case_ids=tuple(
                identity.case_id for _, identity in affected_positions
            ),
        )
