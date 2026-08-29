from __future__ import annotations

from pathlib import Path


def test_gate4_core_energy_vertical_slice_exists() -> None:
    assert Path("src/pyspd/core_energy/formulation.py").is_file(), (
        "REQ-G4-CORE: class-based core energy formulation is absent"
    )
