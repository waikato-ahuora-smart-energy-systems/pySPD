from __future__ import annotations

import math
from pathlib import Path

import pytest

from pyspd.data import (
    CanonicalArchive,
    CanonicalIntegrityError,
    RawRecord,
    RawSymbol,
    RawSymbols,
    ScalarValue,
    SymbolType,
    ValueKind,
)


def sample_symbols() -> RawSymbols:
    return RawSymbols(
        source_name="sample.gdx",
        source_sha256="a" * 64,
        symbols=(
            RawSymbol(
                name="nodes",
                symbol_type=SymbolType.SET,
                dimension=1,
                domains=("*",),
                description="ordered nodes",
                uel_orders=(("N2", "N1", "N3"),),
                records=(
                    RawRecord(("N2",), {"element_text": ScalarValue.text("two")}),
                    RawRecord(("N1",), {"element_text": ScalarValue.text("")}),
                ),
            ),
            RawSymbol(
                name="quantity",
                symbol_type=SymbolType.PARAMETER,
                dimension=1,
                domains=("nodes",),
                description="MW",
                uel_orders=(("N2", "N1", "N3"),),
                records=(
                    RawRecord(("N2",), {"value": ScalarValue.finite(0.0)}),
                    RawRecord(("N1",), {"value": ScalarValue.special(ValueKind.EPS)}),
                    RawRecord(
                        ("N3",),
                        {"value": ScalarValue.special(ValueKind.POSITIVE_INFINITY)},
                    ),
                ),
            ),
        ),
    )


def test_special_values_sparse_presence_and_order_round_trip(tmp_path: Path) -> None:
    source = sample_symbols()
    archive = CanonicalArchive.write(source, tmp_path / "canonical")
    restored = CanonicalArchive.read(archive.root)

    assert restored == source
    assert restored.logical_sha256 == source.logical_sha256
    assert restored["nodes"].uel_orders[0] == ("N2", "N1", "N3")
    assert ("N3",) not in {record.keys for record in restored["nodes"].records}
    values = [record.values["value"] for record in restored["quantity"].records]
    assert values[0].kind is ValueKind.FINITE and values[0].number == 0.0
    assert values[1].kind is ValueKind.EPS and values[1].number is None
    assert values[2].kind is ValueKind.POSITIVE_INFINITY


def test_all_special_value_kinds_are_distinct() -> None:
    values = {
        ScalarValue.special(ValueKind.EPS),
        ScalarValue.special(ValueKind.NA),
        ScalarValue.special(ValueKind.UNDEF),
        ScalarValue.special(ValueKind.POSITIVE_INFINITY),
        ScalarValue.special(ValueKind.NEGATIVE_INFINITY),
    }

    assert len(values) == 5
    assert ScalarValue.finite(-0.0) == ScalarValue.finite(0.0)
    with pytest.raises(ValueError, match="finite"):
        ScalarValue.finite(math.nan)


def test_raw_models_are_immutable_and_reject_duplicate_symbols() -> None:
    source = sample_symbols()

    with pytest.raises((AttributeError, TypeError)):
        source.symbols += (source.symbols[0],)  # type: ignore[misc]
    with pytest.raises(ValueError, match="duplicate symbol"):
        RawSymbols(
            source_name="bad.gdx",
            source_sha256="b" * 64,
            symbols=(source.symbols[0], source.symbols[0]),
        )


def test_archive_fails_closed_when_parquet_is_changed(tmp_path: Path) -> None:
    archive = CanonicalArchive.write(sample_symbols(), tmp_path / "canonical")
    with archive.records_path.open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(CanonicalIntegrityError, match="physical SHA-256"):
        CanonicalArchive.read(archive.root)
