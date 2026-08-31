"""Probity tests for Gate 12 bus-dual null-space certificates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.gate12.bus_price_degeneracy import (
    BusPriceDegeneracyResult,
    BusPriceDegeneracyResultStore,
    BusPriceDegeneracyValidator,
)
from tools.gate12.evidence import EvidenceContractError


def test_opposite_bus_deltas_on_one_node_are_certified() -> None:
    prefix = ("case", "date")
    result = BusPriceDegeneracyValidator().compare_case(
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

    assert result.passed
    assert result.maximum_raw_bus_absolute_difference == pytest.approx(1.0)
    assert result.maximum_repaired_bus_absolute_difference == pytest.approx(1.0)
    assert result.maximum_raw_projected_node_difference == pytest.approx(0.0)
    assert result.maximum_projection_residual == pytest.approx(0.0)


def test_material_node_delta_is_not_certified() -> None:
    prefix = ("case", "date")
    result = BusPriceDegeneracyValidator().compare_case(
        case_id="case",
        raw_reference={(*prefix, "B1"): 10.0},
        raw_candidate={(*prefix, "B1"): 10.1},
        repaired_reference={(*prefix, "B1"): 10.0},
        repaired_candidate={(*prefix, "B1"): 10.1},
        node_reference={(*prefix, "N1"): 10.0},
        node_candidate={(*prefix, "N1"): 10.1},
        node_bus_allocation={(*prefix, "N1", "B1"): 1.0},
    )

    assert not result.passed
    assert result.maximum_node_absolute_difference == pytest.approx(0.1)


def test_projection_must_reproduce_the_observed_node_delta() -> None:
    prefix = ("case", "date")
    result = BusPriceDegeneracyValidator().compare_case(
        case_id="case",
        raw_reference={(*prefix, "B1"): 10.0},
        raw_candidate={(*prefix, "B1"): 10.0},
        repaired_reference={(*prefix, "B1"): 10.0},
        repaired_candidate={(*prefix, "B1"): 10.0},
        node_reference={(*prefix, "N1"): 10.0},
        node_candidate={(*prefix, "N1"): 10.0 + 1e-6},
        node_bus_allocation={(*prefix, "N1", "B1"): 1.0},
    )

    assert not result.passed
    assert result.maximum_projection_residual == pytest.approx(1e-6)


def test_raw_sentinel_is_normalized_only_through_matching_repaired_bus() -> None:
    prefix = ("case", "date")
    result = BusPriceDegeneracyValidator().compare_case(
        case_id="case",
        raw_reference={(*prefix, "B1"): 0.0},
        raw_candidate={(*prefix, "B1"): -500_000.0},
        repaired_reference={(*prefix, "B1"): 0.0},
        repaired_candidate={(*prefix, "B1"): 0.0},
        node_reference={(*prefix, "N1"): 0.0},
        node_candidate={(*prefix, "N1"): 0.0},
        node_bus_allocation={(*prefix, "N1", "B1"): 1.0},
    )

    assert result.passed
    assert result.normalized_raw_sentinel_count == 1
    assert result.maximum_raw_bus_absolute_difference == 500_000.0
    assert result.maximum_raw_projected_node_difference == 0.0


def test_certificate_rejects_identity_or_allocation_gaps() -> None:
    prefix = ("case", "date")
    validator = BusPriceDegeneracyValidator()

    with pytest.raises(EvidenceContractError, match="bus identities"):
        validator.compare_case(
            case_id="case",
            raw_reference={(*prefix, "B1"): 10.0},
            raw_candidate={(*prefix, "B2"): 10.0},
            repaired_reference={(*prefix, "B1"): 10.0},
            repaired_candidate={(*prefix, "B1"): 10.0},
            node_reference={(*prefix, "N1"): 10.0},
            node_candidate={(*prefix, "N1"): 10.0},
            node_bus_allocation={(*prefix, "N1", "B1"): 1.0},
        )

    with pytest.raises(EvidenceContractError, match="allocation"):
        validator.compare_case(
            case_id="case",
            raw_reference={(*prefix, "B1"): 10.0},
            raw_candidate={(*prefix, "B1"): 10.0},
            repaired_reference={(*prefix, "B1"): 10.0},
            repaired_candidate={(*prefix, "B1"): 10.0},
            node_reference={(*prefix, "N1"): 10.0},
            node_candidate={(*prefix, "N1"): 10.0},
            node_bus_allocation={},
        )


def test_daily_certificate_is_hash_bound_and_tamper_evident(tmp_path: Path) -> None:
    prefix = ("case", "date")
    case = BusPriceDegeneracyValidator().compare_case(
        case_id="case",
        raw_reference={(*prefix, "B1"): 10.0},
        raw_candidate={(*prefix, "B1"): 10.0},
        repaired_reference={(*prefix, "B1"): 10.0},
        repaired_candidate={(*prefix, "B1"): 10.0},
        node_reference={(*prefix, "N1"): 10.0},
        node_candidate={(*prefix, "N1"): 10.0},
        node_bus_allocation={(*prefix, "N1", "B1"): 1.0},
    )
    result = BusPriceDegeneracyResult.create(
        trading_date="20221106",
        source_sha256="1" * 64,
        reference_bundle_sha256="2" * 64,
        candidate_bundle_sha256="3" * 64,
        cases=(case,),
    )
    target = tmp_path / "certificate.json"
    store = BusPriceDegeneracyResultStore()
    store.write(result, target)

    assert store.load(target) == result
    payload = json.loads(target.read_text())
    payload["source_sha256"] = "4" * 64
    target.write_text(json.dumps(payload))
    with pytest.raises(EvidenceContractError, match="invalid certificate"):
        store.load(target)
