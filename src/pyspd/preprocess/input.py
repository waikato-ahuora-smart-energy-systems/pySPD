"""Faithful numeric/set access to a selected canonical vSPD case."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pyspd.contracts import CaseData
from pyspd.data import RawSymbol, ValueKind
from pyspd.preprocess.base import Key, PreprocessingError

ALIASES = {
    "i_dateTimeNodetoNode": ("i_dateTimeNodetoNode", "i_dateTimeNodeToNode"),
}


@dataclass(frozen=True, slots=True)
class CaseInput:
    case_data: CaseData

    @property
    def case_id(self) -> str:
        return self.case_data.identifier.case_id

    def symbol(self, name: str) -> RawSymbol:
        candidates = ALIASES.get(name, (name,))
        for candidate in candidates:
            try:
                return self.case_data.symbols[candidate]
            except KeyError:
                continue
        raise PreprocessingError(f"required input symbol is absent: {name}")

    def has_symbol(self, name: str) -> bool:
        """Return whether a canonical symbol (or one of its aliases) is present."""
        for candidate in ALIASES.get(name, (name,)):
            try:
                self.case_data.symbols[candidate]
            except KeyError:
                continue
            return True
        return False

    def optional_members(self, name: str) -> frozenset[Key]:
        return self.members(name) if self.has_symbol(name) else frozenset()

    def optional_numeric(self, name: str) -> dict[Key, float]:
        return self.numeric(name) if self.has_symbol(name) else {}

    def optional_component(self, name: str, component: str) -> dict[Key, float]:
        return self.component(name, component) if self.has_symbol(name) else {}

    def members(self, name: str) -> frozenset[Key]:
        return frozenset(record.keys for record in self.symbol(name).records)

    def numeric(self, name: str) -> dict[Key, float]:
        values: dict[Key, float] = {}
        for record in self.symbol(name).records:
            scalar = record.values.get("value")
            if scalar is None:
                continue
            if scalar.kind is ValueKind.FINITE:
                assert scalar.number is not None
                values[record.keys] = scalar.number
            elif scalar.kind is ValueKind.EPS:
                values[record.keys] = 0.0
            else:
                raise PreprocessingError(
                    f"{name}{record.keys} contains unsupported {scalar.kind.value}"
                )
        return values

    def component(self, name: str, component: str) -> dict[Key, float]:
        wanted = component.casefold()
        return {
            key[:-1]: value
            for key, value in self.numeric(name).items()
            if key[-1].casefold() == wanted
        }

    def gdx_date(self) -> date:
        components = {
            key[-1].casefold(): int(value)
            for key, value in self.numeric("i_gdxDate").items()
        }
        try:
            return date(components["year"], components["month"], components["day"])
        except (KeyError, ValueError) as error:
            raise PreprocessingError(f"invalid i_gdxDate: {components}") from error


def nonzero(value: float) -> bool:
    return value != 0.0
