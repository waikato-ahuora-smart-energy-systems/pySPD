from __future__ import annotations

import math

from pyspd.data import GdxAdapter, ValueKind


class FakeSpecialValues:
    EPS = object()
    NA = object()
    UNDEF = object()
    POSINF = object()
    NEGINF = object()

    @staticmethod
    def isEps(value: object) -> bool:
        return value is FakeSpecialValues.EPS

    @staticmethod
    def isNA(value: object) -> bool:
        return value is FakeSpecialValues.NA

    @staticmethod
    def isUndef(value: object) -> bool:
        return value is FakeSpecialValues.UNDEF

    @staticmethod
    def isPosInf(value: object) -> bool:
        return value is FakeSpecialValues.POSINF

    @staticmethod
    def isNegInf(value: object) -> bool:
        return value is FakeSpecialValues.NEGINF


def test_gams_special_values_are_classified_before_numeric_coercion() -> None:
    cases = {
        FakeSpecialValues.EPS: ValueKind.EPS,
        FakeSpecialValues.NA: ValueKind.NA,
        FakeSpecialValues.UNDEF: ValueKind.UNDEF,
        FakeSpecialValues.POSINF: ValueKind.POSITIVE_INFINITY,
        FakeSpecialValues.NEGINF: ValueKind.NEGATIVE_INFINITY,
    }

    for raw, expected in cases.items():
        assert GdxAdapter.classify_numeric(raw, FakeSpecialValues).kind is expected
    assert GdxAdapter.classify_numeric(2.5, FakeSpecialValues).number == 2.5

    try:
        GdxAdapter.classify_numeric(math.nan, FakeSpecialValues)
    except ValueError as error:
        assert "unclassified non-finite" in str(error)
    else:
        raise AssertionError("ordinary NaN must not silently become NA or UNDEF")
