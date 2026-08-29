from __future__ import annotations

from dataclasses import replace

from pyspd.architecture import ModelAssembler, RebuildDecision, StructuralRebuildPolicy
from pyspd.core_energy import core_energy_formulation
from tests.core_energy.conftest import make_core_case


def test_semantic_signature_changes_with_active_domain() -> None:
    base = make_core_case()
    added_offer = ("C1", "T1", "G2")
    added_block = (*added_offer, "B1")
    changed = replace(
        base,
        offers=base.offers | {added_offer},
        offer_blocks=base.offer_blocks | {added_block},
        offer_region={**base.offer_region, added_offer: next(iter(base.regions))},
        offer_limit={**base.offer_limit, added_block: 10.0},
        offer_price={**base.offer_price, added_block: 30.0},
        generation_start={**base.generation_start, added_offer: 0.0},
        ramp_rate_up={**base.ramp_rate_up, added_offer: 100.0},
        ramp_rate_down={**base.ramp_rate_down, added_offer: 100.0},
        generation_maximum={**base.generation_maximum, added_offer: 10.0},
    )
    assembler = ModelAssembler()
    original = assembler.assemble(core_energy_formulation(), base)
    updated = assembler.assemble(core_energy_formulation(), changed)
    assert original.structural_signature != updated.structural_signature
    comparison = StructuralRebuildPolicy().compare(original, updated)
    assert comparison.decision is RebuildDecision.REBUILD
    assert "active model structure changed" in comparison.reason


def test_nonstructural_value_change_is_reusable_but_stale_state_is_invalidated() -> (
    None
):
    base = make_core_case()
    changed = replace(
        base,
        required_load={key: value + 1.0 for key, value in base.required_load.items()},
    )
    assembler = ModelAssembler()
    original = assembler.assemble(core_energy_formulation(), base)
    updated = assembler.assemble(core_energy_formulation(), changed)
    comparison = StructuralRebuildPolicy().compare(original, updated)
    assert comparison.decision is RebuildDecision.REUSE
    assert comparison.invalidate == frozenset(
        {"primal", "dual", "basis", "fixed_discrete", "solution_loader"}
    )
