"""Fail-closed source-date compatibility for SPD Formulation v16."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

SPD16_FORMULATION_ID = "spd-v16.0-reserve"
SPD16_EFFECTIVE_DATE = date(2026, 6, 23)


class Spd16CompatibilityError(ValueError):
    """A source is outside the declared SPD v16 compatibility boundary."""


@dataclass(frozen=True, slots=True)
class Spd16CompatibilityPolicy:
    effective_date: date = SPD16_EFFECTIVE_DATE

    def validate(self, formulation_id: str, source_date: date) -> None:
        if formulation_id != SPD16_FORMULATION_ID:
            raise Spd16CompatibilityError(
                f"unsupported SPD v16 formulation: {formulation_id}"
            )
        if source_date < self.effective_date:
            raise Spd16CompatibilityError(
                f"source date {source_date.isoformat()} is before SPD v16 "
                f"effective date {self.effective_date.isoformat()}"
            )
