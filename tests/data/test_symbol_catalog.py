from __future__ import annotations

from dataclasses import replace

import pytest

from pyspd.data import RawSymbol, RawSymbols, SymbolCatalog, SymbolCatalogError


def empty_source(catalog: SymbolCatalog) -> RawSymbols:
    return RawSymbols(
        "empty-profile.gdx",
        "a" * 64,
        tuple(
            RawSymbol(
                name=spec.name,
                symbol_type=spec.symbol_type,
                dimension=spec.dimension,
                domains=spec.domains,
                description="catalog fixture",
                uel_orders=tuple(() for _ in range(spec.dimension)),
                records=(),
            )
            for spec in catalog.symbols
        ),
    )


def test_v5_catalog_documents_and_accepts_all_42_symbols() -> None:
    catalog = SymbolCatalog.vspd_v5()

    assert len(catalog.symbols) == 43
    assert all(
        spec.units and spec.consumer and spec.missingness and spec.ordering
        for spec in catalog.symbols
    )
    assert "absence" in catalog.missingness
    assert "UEL" in catalog.ordering
    catalog.validate(empty_source(catalog))


def test_catalog_rejects_missing_unexpected_and_mismatched_symbols() -> None:
    catalog = SymbolCatalog.vspd_v5()
    valid = empty_source(catalog)

    with pytest.raises(SymbolCatalogError, match="missing.*i_gdxDate"):
        catalog.validate(replace(valid, symbols=valid.symbols[1:]))
    with pytest.raises(SymbolCatalogError, match="dimension.*i_gdxDate"):
        bad = replace(
            valid.symbols[0],
            dimension=2,
            domains=("*", "*"),
            uel_orders=((), ()),
        )
        catalog.validate(replace(valid, symbols=(bad, *valid.symbols[1:])))
