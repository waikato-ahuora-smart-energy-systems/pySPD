"""Probity tests for historical CPLEX zero-flow endpoint analysis."""

from __future__ import annotations

import pytest

from tools.analyze_cplex_zero_flow import (
    EndpointSide,
    classify_endpoint,
    export_delta_from_load_endpoint,
)


def test_corpus_scope_is_derived_from_inventory() -> None:
    from tools.analyze_cplex_zero_flow import corpus_scope

    assert corpus_scope(10) == "All 10 deterministic CPLEX reference-corpus days"


def test_classifies_both_loss_kink_endpoints() -> None:
    parent = 100.0
    factor = 0.001

    assert classify_endpoint(parent, parent * (1.0 - factor)) is EndpointSide.EXPORT
    assert (
        classify_endpoint(parent, parent / (1.0 - factor)) is EndpointSide.LOAD
    )


def test_endpoint_classification_is_sign_independent() -> None:
    parent = -100.0
    factor = 0.001

    assert classify_endpoint(parent, parent * (1.0 - factor)) is EndpointSide.EXPORT
    assert (
        classify_endpoint(parent, parent / (1.0 - factor)) is EndpointSide.LOAD
    )


def test_export_projection_from_load_endpoint_is_exact() -> None:
    parent = 100.0
    load = parent / 0.999

    assert export_delta_from_load_endpoint(parent, load) == pytest.approx(
        parent * 0.999 - load
    )


@pytest.mark.parametrize("parent, leaf", [(0.0, 1.0), (10.0, -10.0), (10.0, 10.0)])
def test_non_identifiable_endpoint_is_ambiguous(parent: float, leaf: float) -> None:
    assert classify_endpoint(parent, leaf) is EndpointSide.AMBIGUOUS
