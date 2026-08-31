"""Probity tests for qualified alternative published-price certificates."""

from __future__ import annotations

import pytest

from tools.gate12.published_price_degeneracy import (
    PublishedPriceAlternativeValidator,
)


def test_qualified_alternative_matching_oracle_is_certified() -> None:
    result = PublishedPriceAlternativeValidator().compare(
        product="energy",
        identity=("TP35", "WPT1101"),
        reference=13.18203,
        governed_candidate=13.18102,
        qualified_alternative=13.18202,
        all_cases_complete=True,
        fallback_count=0,
    )

    assert result.passed
    assert result.governed_absolute_error == pytest.approx(0.00101)
    assert result.alternative_absolute_error == pytest.approx(0.00001)
    assert result.reference_within_observed_envelope


def test_alternative_outside_tolerance_or_with_fallback_is_rejected() -> None:
    validator = PublishedPriceAlternativeValidator()
    outside = validator.compare(
        product="energy",
        identity=("TP35", "WPT1101"),
        reference=13.18203,
        governed_candidate=13.18102,
        qualified_alternative=13.18150,
        all_cases_complete=True,
        fallback_count=0,
    )
    fallback = validator.compare(
        product="energy",
        identity=("TP35", "WPT1101"),
        reference=13.18203,
        governed_candidate=13.18102,
        qualified_alternative=13.18202,
        all_cases_complete=True,
        fallback_count=1,
    )

    assert not outside.passed
    assert not fallback.passed
