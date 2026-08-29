from __future__ import annotations

from pyspd.architecture import ModelAssembler
from pyspd.reserve import reserve_formulation
from tests.reserve.conftest import make_reserve_case

V5_STRUCTURAL_SIGNATURE = (
    "592a972925b1d4b44d3253d7dd8f1a7c1ccdfa857b48b7b3aabb844837c47801"
)


def test_v5_structural_fingerprint_is_not_silently_changed() -> None:
    built = ModelAssembler().assemble(reserve_formulation(), make_reserve_case())
    assert built.structural_signature == V5_STRUCTURAL_SIGNATURE
