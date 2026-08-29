from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyspd.data import CanonicalFeed, GdxAdapter, SymbolCatalog


@pytest.mark.oracle
def test_gdx_converts_directly_to_lazy_canonical_feed(tmp_path: Path) -> None:
    source_text = os.environ.get("PYSPD_TEST_GDX")
    system_text = os.environ.get("GAMS_SYSTEM_DIRECTORY")
    if not source_text or not system_text:
        pytest.skip("PYSPD_TEST_GDX and GAMS_SYSTEM_DIRECTORY are required")

    feed = GdxAdapter.write_feed(
        Path(source_text),
        tmp_path / "feed",
        system_directory=Path(system_text),
    )
    reopened = CanonicalFeed.open(feed.root)
    assert reopened.symbol_names
    reference = GdxAdapter.read(
        Path(source_text), system_directory=Path(system_text)
    )
    assert tuple(reopened.read_symbol(name) for name in reopened.symbol_names) == (
        reference.symbols
    )
    raw = reopened.read_case(reopened.read_symbol("i_caseDefn").records[0].keys[0])
    SymbolCatalog.vspd_v5().validate(raw)
    assert raw.source_sha256 == reopened.source_sha256
