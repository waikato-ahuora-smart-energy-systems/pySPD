from __future__ import annotations

from pathlib import Path


def test_gate6_hvdc_and_mip_pricing_vertical_slice_exists() -> None:
    assert Path("src/pyspd/hvdc/formulation.py").is_file(), (
        "REQ-G6-HVDC: class-based HVDC and MIP-pricing formulation is absent"
    )
