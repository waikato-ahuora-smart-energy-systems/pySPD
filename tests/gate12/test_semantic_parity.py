"""Probity tests for compact, policy-bound Gate 12 semantic parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.gate12.bus_price_degeneracy import BusPriceDegeneracyValidator
from tools.gate12.evidence import REQUIRED_E2E_SURFACES, EvidenceContractError
from tools.gate12.incremental_replay import IncrementalReplayWorkItem
from tools.gate12.pyspd_surfaces import CanonicalCaseSurfaces
from tools.gate12.replay_artifacts import (
    CanonicalReplayBundle,
    CanonicalReplayBundleStore,
)
from tools.gate12.semantic_parity import (
    SemanticCaseComparator,
    SemanticParityPolicy,
    SemanticReplayResultStore,
    SemanticReplayValidator,
)


def _json(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _mapping(*rows: tuple[str, float]) -> bytes:
    return _json(
        [
            {"identity": [identity], "value": value.hex()}
            for identity, value in rows
        ]
    )


def _work_item() -> IncrementalReplayWorkItem:
    return IncrementalReplayWorkItem.create(
        trading_date="20221106",
        source_sha256="1" * 64,
        discovery_checkpoint_sha256="2" * 64,
        case_ids=("affected",),
        affected_case_ids=("affected",),
    )


def _write_bundle(root: Path, profile: str, *, node_price: float) -> None:
    surfaces = {
        surface: _json({"value": 1.0}) for surface in REQUIRED_E2E_SURFACES
    }
    surfaces["node-price"] = _mapping(("NODE", node_price))
    case = CanonicalCaseSurfaces(
        case_id="affected",
        trading_date="20221106",
        surfaces=surfaces,
    )
    bundle = CanonicalReplayBundle.create(
        engine_profile=profile,
        execution_sha256="e" * 64,
        work_item=_work_item(),
        cases=(case,),
    )
    CanonicalReplayBundleStore(root).write(bundle=bundle, cases=(case,))


def test_semantic_comparator_accepts_tolerance_and_sparse_zero() -> None:
    result = SemanticCaseComparator(SemanticParityPolicy()).compare_surface(
        surface="primary-physics",
        reference=_mapping(("A", 10.0), ("ZERO", 0.0)),
        candidate=_mapping(("A", 10.0 + 5e-9)),
    )

    assert result.passed
    assert result.unresolved_difference_count == 0
    assert result.accepted_reason_counts == {
        "sparse-zero": 1,
        "within-tolerance": 1,
    }


def test_semantic_comparator_rejects_material_numeric_difference() -> None:
    result = SemanticCaseComparator(SemanticParityPolicy()).compare_surface(
        surface="node-price",
        reference=_mapping(("A", 10.0)),
        candidate=_mapping(("A", 10.001)),
    )

    assert not result.passed
    assert result.unresolved_difference_count == 1
    assert result.maximum_unresolved_absolute_error == pytest.approx(0.001)
    assert result.unresolved_examples[0].path[-1] == "value"


def test_semantic_comparator_uses_fixed_rmip_as_accepted_objective() -> None:
    result = SemanticCaseComparator(SemanticParityPolicy()).compare_surface(
        surface="primary-objective",
        reference=_json(
            {
                "fixed_rmip_objective_nzd": (-100.0).hex(),
                "primary_mip_objective_nzd": (-100.0).hex(),
            }
        ),
        candidate=_json(
            {
                "fixed_rmip_objective_nzd": (-100.0 + 1e-8).hex(),
                "primary_mip_objective_nzd": (-99.5).hex(),
            }
        ),
    )

    assert result.passed
    assert result.accepted_reason_counts == {
        "qualified-primary-mip-diagnostic": 1,
        "within-tolerance": 1,
    }
    assert result.maximum_absolute_error == pytest.approx(0.5)


def test_raw_sentinel_requires_matching_repaired_economics() -> None:
    comparator = SemanticCaseComparator(SemanticParityPolicy())
    accepted = comparator.compare_surface(
        surface="raw-bus-price",
        reference=_mapping(("BUS", 500_000.0)),
        candidate=_mapping(("BUS", 10.0)),
        repaired_reference=_mapping(("BUS", 10.0)),
        repaired_candidate=_mapping(("BUS", 10.0 + 1e-8)),
    )
    rejected = comparator.compare_surface(
        surface="raw-bus-price",
        reference=_mapping(("BUS", 500_000.0)),
        candidate=_mapping(("BUS", 10.0)),
        repaired_reference=_mapping(("BUS", 10.0)),
        repaired_candidate=_mapping(("BUS", 10.1)),
    )

    assert accepted.passed
    assert accepted.accepted_reason_counts == {"raw-sentinel-normalized": 1}
    assert not rejected.passed


def test_raw_sentinel_uses_its_exact_repaired_path_when_another_bus_differs() -> None:
    result = SemanticCaseComparator(SemanticParityPolicy()).compare_surface(
        surface="raw-bus-price",
        reference=_mapping(("SENTINEL", 0.0), ("OTHER", 10.0)),
        candidate=_mapping(("SENTINEL", -500_000.0), ("OTHER", 10.0)),
        repaired_reference=_mapping(("SENTINEL", 0.0), ("OTHER", 10.0)),
        repaired_candidate=_mapping(("SENTINEL", 0.0), ("OTHER", 10.1)),
    )

    assert result.passed
    assert result.accepted_reason_counts == {"raw-sentinel-normalized": 1}


def test_report_schema_difference_stays_explicitly_unresolved() -> None:
    result = SemanticCaseComparator(SemanticParityPolicy()).compare_surface(
        surface="report-field",
        reference=_json({"AuthorityTable": {"rows": []}}),
        candidate=_json({"node": {"rows": []}}),
    )

    assert not result.passed
    assert result.unresolved_difference_count == 1
    assert result.unresolved_reason_counts == {"report-crosswalk-required": 1}


def test_passing_case_certificate_resolves_only_numeric_bus_delta() -> None:
    prefix = ("case", "date")
    certificate = BusPriceDegeneracyValidator().compare_case(
        case_id="case",
        raw_reference={(*prefix, "B1"): 10.0, (*prefix, "B2"): 20.0},
        raw_candidate={(*prefix, "B1"): 11.0, (*prefix, "B2"): 19.0},
        repaired_reference={(*prefix, "B1"): 10.0, (*prefix, "B2"): 20.0},
        repaired_candidate={(*prefix, "B1"): 11.0, (*prefix, "B2"): 19.0},
        node_reference={(*prefix, "N1"): 15.0},
        node_candidate={(*prefix, "N1"): 15.0},
        node_bus_allocation={
            (*prefix, "N1", "B1"): 0.5,
            (*prefix, "N1", "B2"): 0.5,
        },
    )
    result = SemanticCaseComparator(SemanticParityPolicy()).compare_surface(
        surface="repaired-bus-price",
        reference=_mapping(("B1", 10.0), ("B2", 20.0)),
        candidate=_mapping(("B1", 11.0), ("B2", 19.0)),
        bus_price_certificate=certificate,
    )

    assert result.passed
    assert result.accepted_reason_counts == {
        "node-allocation-nullspace-certificate": 2
    }


def test_exact_control_surface_is_not_relaxed() -> None:
    result = SemanticCaseComparator(SemanticParityPolicy()).compare_surface(
        surface="state-transition",
        reference=_json({"status": "complete"}),
        candidate=_json({"status": "different"}),
    )

    assert not result.passed
    assert result.unresolved_reason_counts == {"exact-mismatch": 1}


def test_semantic_bundle_result_is_hash_bound_and_immutable(tmp_path: Path) -> None:
    _write_bundle(tmp_path / "reference", "gams-v502", node_price=10.0)
    _write_bundle(tmp_path / "candidate", "pyspd-v1", node_price=10.0 + 1e-8)

    result = SemanticReplayValidator(
        reference_root=tmp_path / "reference",
        candidate_root=tmp_path / "candidate",
    ).compare("20221106")
    target = tmp_path / "semantic" / "20221106.json"
    store = SemanticReplayResultStore()
    store.write(result, target)

    assert result.passed
    assert len(result.logical_sha256) == 64
    assert json.loads(target.read_text())["logical_sha256"] == result.logical_sha256
    with pytest.raises(EvidenceContractError, match="already exists"):
        store.write(result, target)


def test_semantic_policy_rejects_non_finite_tolerances() -> None:
    with pytest.raises(EvidenceContractError, match="finite"):
        SemanticParityPolicy(price_tolerance=float("nan"))
