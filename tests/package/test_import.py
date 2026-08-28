from __future__ import annotations

import importlib.util


def test_pyspd_is_an_installable_src_package() -> None:
    assert importlib.util.find_spec("pyspd") is not None, (
        "REQ-G2-PACKAGE: the pyspd src package is not importable"
    )
