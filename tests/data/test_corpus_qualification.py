from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pyspd.data import CanonicalFeed, RawRecord, RawSymbol, RawSymbols, ScalarValue
from pyspd.data.catalog import SymbolCatalog
from tools.gate2.corpus import CorpusQualifier


def fixture_symbols(source_name: str, source_sha256: str) -> RawSymbols:
    catalog = SymbolCatalog.vspd_v5()
    symbols = [
        RawSymbol(
            spec.name,
            spec.symbol_type,
            spec.dimension,
            spec.domains,
            "corpus fixture",
            tuple(() for _ in range(spec.dimension)),
            (),
        )
        for spec in catalog.symbols
        if spec.required
    ]

    def update(name: str, records: tuple[RawRecord, ...], uels: tuple[tuple[str, ...], ...]) -> None:
        index = next(i for i, symbol in enumerate(symbols) if symbol.name == name)
        symbols[index] = replace(symbols[index], records=records, uel_orders=uels)

    update(
        "i_caseDefn",
        (RawRecord(("C1", "case", "run"), {"element_text": ScalarValue.text("")}),),
        (("C1",), ("case",), ("run",)),
    )
    update(
        "i_dateTimeTradePeriodMap",
        (RawRecord(("C1", "D1", "TP1"), {"element_text": ScalarValue.text("")}),),
        (("C1",), ("D1",), ("TP1",)),
    )
    return RawSymbols(source_name, source_sha256, tuple(symbols))


def test_corpus_qualification_is_resumable_and_hash_bound(tmp_path: Path) -> None:
    input_root = tmp_path / "inputs"
    source = input_root / "2024" / "Pricing_20240101.gdx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"governed input")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "artifact_count": 1,
                "artifacts": [
                    {
                        "trading_date": "20240101",
                        "size_bytes": source.stat().st_size,
                        "sha256": source_sha,
                    }
                ],
            }
        )
    )
    calls: list[Path] = []

    def convert(path: Path, destination: Path) -> CanonicalFeed:
        calls.append(path)
        return CanonicalFeed.write(
            fixture_symbols(path.name, source_sha), destination
        )

    qualifier = CorpusQualifier(convert)
    first = qualifier.run(
        inventory_path=inventory,
        input_root=input_root,
        output_root=tmp_path / "feeds",
        evidence_path=tmp_path / "evidence.json",
    )
    second = qualifier.run(
        inventory_path=inventory,
        input_root=input_root,
        output_root=tmp_path / "feeds",
        evidence_path=tmp_path / "evidence-2.json",
    )

    assert len(calls) == 1
    assert first == second
    assert first["qualified_input_count"] == 1
    assert first["entries"][0]["representative_cases"][0]["case_id"] == "C1"


def test_corpus_qualification_rejects_wrong_raw_hash(tmp_path: Path) -> None:
    source = tmp_path / "inputs" / "2024" / "Pricing_20240101.gdx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"changed")
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "artifact_count": 1,
                "artifacts": [
                    {"trading_date": "20240101", "size_bytes": 7, "sha256": "0" * 64}
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="raw SHA-256.*20240101"):
        CorpusQualifier(lambda _path, _root: None).run(  # type: ignore[arg-type]
            inventory_path=inventory,
            input_root=tmp_path / "inputs",
            output_root=tmp_path / "feeds",
            evidence_path=tmp_path / "evidence.json",
        )
