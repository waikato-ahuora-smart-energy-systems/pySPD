from pathlib import Path


def test_gate7_full_reserve_vertical_slice_exists() -> None:
    assert Path("src/pyspd/reserve/formulation.py").is_file(), (
        "REQ-G7-RESERVE: class-based reserve/risk/NMIR formulation is absent"
    )
