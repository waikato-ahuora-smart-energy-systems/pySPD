from __future__ import annotations

import math

import numpy as np
import pytest

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


class FakeVectorSpecialValues:
    @staticmethod
    def isEps(values: object) -> object:
        return np.asarray(values) == -101.0

    @staticmethod
    def isNA(values: object) -> object:
        return np.asarray(values) == -102.0

    @staticmethod
    def isUndef(values: object) -> object:
        return np.asarray(values) == -103.0

    @staticmethod
    def isPosInf(values: object) -> object:
        return np.asarray(values) == -104.0

    @staticmethod
    def isNegInf(values: object) -> object:
        return np.asarray(values) == -105.0


def test_numeric_column_classification_preserves_order_and_special_semantics() -> None:
    values = GdxAdapter.classify_numeric_column(
        [2.5, -101.0, -102.0, -103.0, -104.0, -105.0, -0.0],
        FakeVectorSpecialValues,
    )

    assert tuple(value.kind for value in values) == (
        ValueKind.FINITE,
        ValueKind.EPS,
        ValueKind.NA,
        ValueKind.UNDEF,
        ValueKind.POSITIVE_INFINITY,
        ValueKind.NEGATIVE_INFINITY,
        ValueKind.FINITE,
    )
    assert values[0].number == 2.5
    assert values[-1].number == 0.0
    assert math.copysign(1.0, values[-1].number or 0.0) == 1.0


def test_numeric_column_rejects_unclassified_nonfinite_and_bad_predicates() -> None:
    with pytest.raises(ValueError, match="unclassified non-finite"):
        GdxAdapter.classify_numeric_column([math.nan], FakeVectorSpecialValues)

    class BadShape(FakeVectorSpecialValues):
        @staticmethod
        def isEps(values: object) -> object:
            del values
            return [False, False]

    with pytest.raises(ValueError, match="incompatible shape"):
        GdxAdapter.classify_numeric_column([1.0], BadShape)


class FakeIloc:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.rows = rows

    def __getitem__(self, key: tuple[slice, int]) -> list[object]:
        _, column = key
        return [row[column] for row in self.rows]


class FakeFrame:
    def __init__(
        self, columns: tuple[str, ...], rows: tuple[tuple[object, ...], ...]
    ) -> None:
        self.columns = columns
        self.rows = rows
        self.iloc = FakeIloc(rows)

    def __len__(self) -> int:
        return len(self.rows)

    def itertuples(self, *, index: bool, name: object) -> object:
        assert not index and name is None
        return iter(self.rows)


class Set:
    dimension = 1
    domain_names = ("*",)
    description = "fixture"

    def __init__(self, value: str) -> None:
        self.records = FakeFrame(("key", "element_text"), ((value, None),))
        self.value = value

    def getUELs(self, *, dimensions: int) -> list[str]:
        assert dimensions == 0
        return [self.value]


class FakeContainer:
    def __init__(self) -> None:
        self.symbols = {"first": Set("A"), "second": Set("B")}

    def listSymbols(self) -> list[str]:
        return list(self.symbols)

    def __getitem__(self, name: str) -> Set:
        return self.symbols[name]


def test_container_conversion_preserves_symbol_names_across_value_columns() -> None:
    raw = GdxAdapter.from_container(
        FakeContainer(),
        source_name="fixture.gdx",
        source_sha256="a" * 64,
        special_values=FakeVectorSpecialValues,
    )

    assert tuple(symbol.name for symbol in raw.symbols) == ("first", "second")
    assert raw["first"].records[0].values["element_text"].string == ""
