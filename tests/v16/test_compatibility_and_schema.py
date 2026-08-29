from __future__ import annotations

from datetime import date

import pytest

from pyspd.data import RawSymbol, RawSymbols, SymbolCatalog
from pyspd.data.raw import SymbolType
from pyspd.v16 import (
    SPD16_EFFECTIVE_DATE,
    SPD16_FORMULATION_ID,
    Spd16CompatibilityError,
    Spd16CompatibilityPolicy,
)


def test_v16_selection_has_an_explicit_effective_date_boundary() -> None:
    policy = Spd16CompatibilityPolicy()

    assert SPD16_EFFECTIVE_DATE == date(2026, 6, 23)
    policy.validate(SPD16_FORMULATION_ID, date(2026, 6, 23))
    with pytest.raises(Spd16CompatibilityError, match="before.*2026-06-23"):
        policy.validate(SPD16_FORMULATION_ID, date(2026, 6, 22))


def test_v16_catalog_adds_the_battery_matching_symbol_without_mutating_v5() -> None:
    v5 = SymbolCatalog.vspd_v5()
    v16 = SymbolCatalog.spd_v16()

    assert len(v5.symbols) == 43
    assert len(v16.symbols) == 44
    match = next(spec for spec in v16.symbols if spec.name == "i_busUnitAndKey3Match")
    assert match.symbol_type is SymbolType.SET
    assert match.dimension == 4
    assert match.domains == ("ca", "dt", "n", "n1")

    source = RawSymbols(
        "empty-v16.gdx",
        "a" * 64,
        tuple(
            RawSymbol(
                spec.name,
                spec.symbol_type,
                spec.dimension,
                spec.domains,
                "v16 catalog fixture",
                tuple(() for _ in range(spec.dimension)),
                (),
            )
            for spec in v16.symbols
        ),
    )
    v16.validate(source)

