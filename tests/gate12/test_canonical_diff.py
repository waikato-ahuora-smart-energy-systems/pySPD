"""Probity tests for quantified Gate 12 canonical bundle differences."""

from __future__ import annotations

import hashlib
import json

import pytest

from tools.gate12.canonical_diff import (
    CanonicalBundleDiffer,
    CanonicalBundleDifferenceStore,
    CanonicalJsonDiffer,
)
from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.incremental_replay import IncrementalReplayWorkItem
from tools.gate12.pyspd_surfaces import CanonicalCaseSurfaces
from tools.gate12.replay_artifacts import (
    CanonicalReplayBundle,
    CanonicalReplayBundleStore,
)


def _json(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _work_item() -> IncrementalReplayWorkItem:
    return IncrementalReplayWorkItem.create(
        trading_date="20221106",
        source_sha256="1" * 64,
        discovery_checkpoint_sha256="2" * 64,
        case_ids=("warmup", "affected"),
        affected_case_ids=("affected",),
    )


def _write_bundle(root, profile: str, changed: bytes | None = None) -> None:
    surfaces = {
        surface: _json({"value": "0x1.0000000000000p+0"})
        for surface in REQUIRED_E2E_SURFACES
    }
    if changed is not None:
        surfaces["node-price"] = changed
    cases = (
        CanonicalCaseSurfaces(
            case_id="affected",
            trading_date="20221106",
            surfaces=surfaces,
        ),
    )
    bundle = CanonicalReplayBundle.create(
        engine_profile=profile,
        execution_sha256="e" * 64,
        work_item=_work_item(),
        cases=cases,
    )
    CanonicalReplayBundleStore(root).write(bundle=bundle, cases=cases)


def test_json_differ_quantifies_numeric_and_structural_changes() -> None:
    reference = _json(
        {
            "same": True,
            "numeric": "0x1.0000000000000p+1",
            "missing": 1,
            "rows": [{"value": "0x1.0000000000000p+0"}],
        }
    )
    candidate = _json(
        {
            "same": True,
            "numeric": "0x1.4000000000000p+1",
            "extra": 1,
            "rows": [{"value": "0x1.8000000000000p+0"}],
        }
    )

    result = CanonicalJsonDiffer().compare(reference, candidate)

    assert not result.identical
    assert result.reference_leaf_count == 4
    assert result.candidate_leaf_count == 4
    assert result.missing_path_count == 1
    assert result.extra_path_count == 1
    assert result.changed_value_count == 2
    assert result.numeric_difference_count == 2
    assert result.maximum_absolute_error == pytest.approx(0.5)
    assert {difference.path for difference in result.differences} == {
        ("extra",),
        ("missing",),
        ("numeric",),
        ("rows", "0", "value"),
    }


def test_json_differ_rejects_invalid_or_non_finite_numeric_evidence() -> None:
    with pytest.raises(EvidenceContractError, match="canonical JSON"):
        CanonicalJsonDiffer().compare(b"not-json", b"{}")
    with pytest.raises(EvidenceContractError, match="non-finite"):
        CanonicalJsonDiffer().compare(_json({"value": 1e999}), _json({"value": 1}))


def test_json_differ_exposes_canonical_encoding_drift() -> None:
    result = CanonicalJsonDiffer().compare(b'{"value":1}\n', _json({"value": 1}))

    assert not result.identical
    assert result.unresolved_difference_count == 1
    assert result.differences[0].kind == "encoding"
    assert result.differences[0].path == ()


def test_json_differ_aligns_canonical_mapping_rows_by_identity() -> None:
    reference = _json(
        {
            "rows": [
                {"identity": ["A"], "value": "0x1.0000000000000p+0"},
                {"identity": ["B"], "value": "0x1.0000000000000p+1"},
            ]
        }
    )
    candidate = _json(
        {
            "rows": [
                {"identity": ["C"], "value": "0x1.8000000000000p+1"},
                {"identity": ["A"], "value": "0x1.0000000000000p+0"},
            ]
        }
    )

    result = CanonicalJsonDiffer().compare(reference, candidate)

    assert result.missing_path_count == 1
    assert result.extra_path_count == 1
    assert result.changed_value_count == 0
    assert result.numeric_difference_count == 0
    assert result.maximum_absolute_error == 0.0
    assert {difference.reference for difference in result.differences} == {
        None,
        "0x1.0000000000000p+1",
    }
    assert {difference.candidate for difference in result.differences} == {
        None,
        "0x1.8000000000000p+1",
    }


def test_bundle_differ_emits_hash_bound_path_level_evidence(tmp_path) -> None:
    _write_bundle(tmp_path / "reference", "gams-v502")
    _write_bundle(
        tmp_path / "candidate",
        "pyspd-v1",
        changed=_json(
            {
                "value": "0x1.8000000000000p+0",
                "candidate_only": "diagnostic",
            }
        ),
    )

    result = CanonicalBundleDiffer(
        reference_root=tmp_path / "reference",
        candidate_root=tmp_path / "candidate",
    ).compare("20221106")

    assert not result.identical
    assert result.changed_surface_count == 1
    assert result.unresolved_difference_count == 2
    assert result.maximum_absolute_error == pytest.approx(0.5)
    assert len(result.logical_sha256) == 64
    surface = result.cases[0].surfaces["node-price"]
    assert surface.extra_path_count == 1
    assert surface.numeric_difference_count == 1


def test_bundle_differ_rejects_different_work_item_provenance(tmp_path) -> None:
    _write_bundle(tmp_path / "reference", "gams-v502")
    _write_bundle(tmp_path / "candidate", "pyspd-v1")
    manifest = tmp_path / "candidate" / "20221106" / "bundle.json"
    payload = json.loads(manifest.read_text())
    payload["work_item_sha256"] = "3" * 64
    unsigned = dict(payload)
    unsigned.pop("logical_sha256")
    payload["logical_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    with pytest.raises(EvidenceContractError, match="provenance"):
        CanonicalBundleDiffer(
            reference_root=tmp_path / "reference",
            candidate_root=tmp_path / "candidate",
        ).compare("20221106")


def test_quantified_difference_store_is_atomic_and_immutable(tmp_path) -> None:
    _write_bundle(tmp_path / "reference", "gams-v502")
    _write_bundle(tmp_path / "candidate", "pyspd-v1")
    result = CanonicalBundleDiffer(
        reference_root=tmp_path / "reference",
        candidate_root=tmp_path / "candidate",
    ).compare("20221106")
    target = tmp_path / "diffs" / "20221106.json"

    CanonicalBundleDifferenceStore().write(result, target)

    payload = json.loads(target.read_text())
    assert payload["identical"] is True
    assert payload["logical_sha256"] == result.logical_sha256
    with pytest.raises(EvidenceContractError, match="already exists"):
        CanonicalBundleDifferenceStore().write(result, target)
