"""Explicit scalar semantics for GAMS values and text attributes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ValueKind(StrEnum):
    FINITE = "finite"
    EPS = "eps"
    NA = "na"
    UNDEF = "undef"
    POSITIVE_INFINITY = "positive_infinity"
    NEGATIVE_INFINITY = "negative_infinity"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class ScalarValue:
    kind: ValueKind
    number: float | None = None
    string: str | None = None

    def __post_init__(self) -> None:
        if self.kind is ValueKind.FINITE:
            if self.number is None or not math.isfinite(self.number):
                raise ValueError("finite scalar requires a finite number")
            if self.string is not None:
                raise ValueError("finite scalar cannot contain text")
        elif self.kind is ValueKind.TEXT:
            if self.string is None or self.number is not None:
                raise ValueError("text scalar requires only text")
        elif self.number is not None or self.string is not None:
            raise ValueError("special scalar cannot contain a payload")

    @classmethod
    def finite(cls, value: float) -> ScalarValue:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("finite scalar requires a finite number")
        if number == 0.0:
            number = 0.0
        return cls(ValueKind.FINITE, number=number)

    @classmethod
    def special(cls, kind: ValueKind) -> ScalarValue:
        if kind in {ValueKind.FINITE, ValueKind.TEXT}:
            raise ValueError("special scalar requires a GAMS special-value kind")
        return cls(kind)

    @classmethod
    def text(cls, value: str) -> ScalarValue:
        return cls(ValueKind.TEXT, string=value)

    def to_wire(self) -> dict[str, str | None]:
        return {
            "kind": self.kind.value,
            "number_hex": self.number.hex() if self.number is not None else None,
            "text": self.string,
        }

    @classmethod
    def from_wire(
        cls, kind: str, number_hex: str | None, text: str | None
    ) -> ScalarValue:
        value_kind = ValueKind(kind)
        number = float.fromhex(number_hex) if number_hex is not None else None
        return cls(value_kind, number=number, string=text)
