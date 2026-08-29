"""Probity tests for prefix-complete Gate 12 affected-case replay plans."""

from __future__ import annotations

import pytest

from tools.gate12.evidence import (
    AffectedIntervalIdentity,
    AffectedIntervalManifest,
    EvidenceContractError,
)
from tools.gate12.historical_population import (
    HISTORICAL_EXECUTION_PROFILE,
    HistoricalGdxCaseIndex,
    HistoricalInputArtifact,
    HistoricalInputInventory,
)
from tools.gate12.replay import (
    HistoricalAffectedManifestLoader,
    HistoricalAffectedReplayPlanner,
)


def _population():
    artifacts = []
    identities = []
    indices = {}
    for date_index in range(139):
        trading_date = f"2022{date_index:04d}"
        source_sha256 = f"{date_index + 1:064x}"
        affected_count = 4 if date_index < 129 else 3
        affected = tuple(
            (f"affected_{date_index}_{case_index}", f"DT-{date_index}-{case_index}")
            for case_index in range(affected_count)
        )
        cases = ((f"warmup_{date_index}", f"DT-{date_index}-warmup"), *affected,
                 (f"tail_{date_index}", f"DT-{date_index}-tail"))
        periods = {case: f"TP-{position}" for position, case in enumerate(cases)}
        indices[trading_date] = HistoricalGdxCaseIndex(cases, periods)
        artifacts.append(HistoricalInputArtifact(trading_date, 1, source_sha256))
        identities.extend(
            AffectedIntervalIdentity(
                case_id=case_id,
                date_time=date_time,
                trading_period=periods[(case_id, date_time)],
                trading_date=trading_date,
                source_sha256=source_sha256,
                discovery_rationale="optimal first-loop historical solve",
            )
            for case_id, date_time in affected
        )
    return (
        AffectedIntervalManifest("v5.0.4", "3360a91", tuple(identities)),
        HistoricalInputInventory(tuple(artifacts)),
        indices,
    )


def test_replay_plan_preserves_prefix_and_excludes_post_affected_tail() -> None:
    manifest, inventory, indices = _population()

    plan = HistoricalAffectedReplayPlanner().plan(
        manifest=manifest,
        inventory=inventory,
        case_indices=indices,
    )

    assert len(plan.batches) == 139
    assert plan.affected_case_count == 546
    assert plan.selected_case_count == 685
    assert plan.batches[0].case_ids[0] == "warmup_0"
    assert plan.batches[0].case_ids[-1] == "affected_0_3"
    assert "tail_0" not in plan.batches[0].case_ids
    assert len(plan.logical_sha256) == 64
    assert plan.to_dict()["logical_sha256"] == plan.logical_sha256


def test_replay_plan_rejects_an_affected_identity_missing_from_gdx_index() -> None:
    manifest, inventory, indices = _population()
    original = indices["20220000"]
    retained = tuple(case for case in original.cases if case[0] != "affected_0_0")
    indices["20220000"] = HistoricalGdxCaseIndex(
        retained,
        {case: original.trading_periods[case] for case in retained},
    )

    with pytest.raises(EvidenceContractError, match="absent from canonical GDX"):
        HistoricalAffectedReplayPlanner().plan(
            manifest=manifest,
            inventory=inventory,
            case_indices=indices,
        )


def test_affected_manifest_loader_is_strict_and_accepts_merge_profile() -> None:
    manifest, _inventory, _indices = _population()
    payload = {
        "schema_version": 1,
        "source_release": manifest.source_release,
        "reference_commit": manifest.reference_commit,
        "execution_profile": HISTORICAL_EXECUTION_PROFILE,
        "identities": [identity.__dict__ for identity in manifest.identities],
    }

    loaded = HistoricalAffectedManifestLoader().from_dict(payload)

    assert loaded == manifest
    payload["execution_profile"] = "thresholded-invalid-profile"
    with pytest.raises(EvidenceContractError, match="execution profile"):
        HistoricalAffectedManifestLoader().from_dict(payload)
    payload["execution_profile"] = HISTORICAL_EXECUTION_PROFILE
    payload["unexpected"] = True
    with pytest.raises(EvidenceContractError, match="manifest schema"):
        HistoricalAffectedManifestLoader().from_dict(payload)
