from __future__ import annotations

from pyspd.architecture import ModelAssembler
from pyspd.reserve import reserve_formulation
from tests.reserve.conftest import make_reserve_case


V5_STRUCTURAL_SIGNATURE = "91f792524354d0649323ba892f5a83e993912496abde7ccfd40eaf2c8d7671b4"


def test_v5_structural_fingerprint_is_not_silently_changed() -> None:
    built = ModelAssembler().assemble(reserve_formulation(), make_reserve_case())
    assert built.structural_signature == V5_STRUCTURAL_SIGNATURE

