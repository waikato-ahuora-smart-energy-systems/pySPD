from __future__ import annotations

from pathlib import Path


def test_gate5_ac_network_vertical_slice_exists() -> None:
    assert Path("src/pyspd/network/formulation.py").is_file(), (
        "REQ-G5-NETWORK: class-based AC network formulation is absent"
    )
