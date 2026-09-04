from __future__ import annotations

from pyspd.architecture import ModelAssembler
from pyspd.reserve import reserve_formulation
from tests.reserve.conftest import make_reserve_case

V5_STRUCTURAL_SIGNATURE = (
    "329a0115c979219589f0ad143bdf3a991dac752e1302a60104910aa8f771764b"
)


def test_v5_structural_fingerprint_is_not_silently_changed() -> None:
    built = ModelAssembler().assemble(reserve_formulation(), make_reserve_case())
    assert built.structural_signature == V5_STRUCTURAL_SIGNATURE
