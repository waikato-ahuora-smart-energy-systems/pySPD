from __future__ import annotations

from pyspd.architecture import ModelAssembler
from pyspd.reserve import reserve_formulation
from tests.reserve.conftest import make_reserve_case

V5_STRUCTURAL_SIGNATURE = (
    "414d7c57c8078217bf0c557f5525ca0325e88c3a7c1183491d2b50b31d296ff8"
)


def test_v5_structural_fingerprint_is_not_silently_changed() -> None:
    built = ModelAssembler().assemble(reserve_formulation(), make_reserve_case())
    assert built.structural_signature == V5_STRUCTURAL_SIGNATURE
