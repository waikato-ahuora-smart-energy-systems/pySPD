from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyspd.data import (
    CanonicalFeed,
    CanonicalFeedError,
    RawRecord,
    RawSymbol,
    RawSymbols,
    ScalarValue,
    SymbolType,
    ValueKind,
)


def source() -> RawSymbols:
    return RawSymbols(
        "feed.gdx",
        "f" * 64,
        (
            RawSymbol(
                "global_nodes",
                SymbolType.SET,
                1,
                ("*",),
                "nodes",
                (("N2", "N1"),),
                (
                    RawRecord(("N2",), {"element_text": ScalarValue.text("")}),
                    RawRecord(("N1",), {"element_text": ScalarValue.text("")}),
                ),
            ),
            RawSymbol(
                "case_quantity",
                SymbolType.PARAMETER,
                2,
                ("caseID", "node"),
                "quantity",
                (("C1", "C2"), ("N2", "N1")),
                (
                    RawRecord(
                        ("C1", "N2"), {"value": ScalarValue.finite(0.0)}
                    ),
                    RawRecord(
                        ("C1", "N1"),
                        {"value": ScalarValue.special(ValueKind.EPS)},
                    ),
                    RawRecord(
                        ("C2", "N1"),
                        {"value": ScalarValue.special(ValueKind.NA)},
                    ),
                ),
            ),
        ),
    )


def test_feed_is_lazy_case_filterable_and_one_row_per_record(tmp_path: Path) -> None:
    feed = CanonicalFeed.write(source(), tmp_path / "feed")
    reopened = CanonicalFeed.open(feed.root)

    assert reopened.symbol_names == ("global_nodes", "case_quantity")
    assert [symbol.records for symbol in reopened.read_schema().symbols] == [(), ()]
    assert reopened.logical_sha256 == feed.logical_sha256
    assert (
        reopened.logical_sha256
        == "6625493ac0680efd0bb106a83aee17212fd3ad11e06f941c8d20958cd7650796"
    )
    assert reopened.read_symbol("case_quantity") == source()["case_quantity"]
    selected = reopened.read_case("C1")
    assert len(selected["global_nodes"].records) == 2
    assert [record.keys for record in selected["case_quantity"].records] == [
        ("C1", "N2"),
        ("C1", "N1"),
    ]
    manifest = json.loads((feed.root / "manifest.json").read_text())
    assert sum(item["record_count"] for item in manifest["symbols"]) == 5
    assert sum(item["parquet_row_count"] for item in manifest["symbols"]) == 5


def test_logical_hash_is_independent_of_parquet_encoding(tmp_path: Path) -> None:
    zstd = CanonicalFeed.write(source(), tmp_path / "zstd", compression="zstd")
    snappy = CanonicalFeed.write(source(), tmp_path / "snappy", compression="snappy")

    assert zstd.logical_sha256 == snappy.logical_sha256
    zstd_manifest = (zstd.root / "manifest.json").read_bytes()
    snappy_manifest = (snappy.root / "manifest.json").read_bytes()
    assert zstd_manifest != snappy_manifest


def test_feed_detects_physical_tampering(tmp_path: Path) -> None:
    feed = CanonicalFeed.write(source(), tmp_path / "feed")
    manifest = json.loads((feed.root / "manifest.json").read_text())
    path = feed.root / manifest["symbols"][0]["path"]
    with path.open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(CanonicalFeedError, match="physical SHA-256"):
        CanonicalFeed.open(feed.root).read_symbol("global_nodes")


def test_feed_rejects_artifact_paths_outside_its_root(tmp_path: Path) -> None:
    feed = CanonicalFeed.write(source(), tmp_path / "feed")
    manifest_path = feed.root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["symbols"][0]["path"] = "../outside.parquet"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(CanonicalFeedError, match="escapes feed root"):
        CanonicalFeed.open(feed.root)
