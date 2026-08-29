from __future__ import annotations

from pyspd.architecture import ModelAssembler
from pyspd.core_energy import CoreEnergyCase, core_energy_formulation
from tests.preprocess.conftest import make_case


def test_gate3_artifacts_project_to_core_energy_without_mutating_case_data() -> None:
    source = make_case()
    symbol_hash = source.symbols.logical_sha256
    built = ModelAssembler().assemble(core_energy_formulation(preprocess=True), source)
    assert isinstance(built.case_data, CoreEnergyCase)
    assert built.case_data.preprocessing_signature
    assert source.symbols.logical_sha256 == symbol_hash
    assert built.case_data.offers
    assert built.case_data.regions == frozenset(
        {("C1", "D1", "NI"), ("C1", "D1", "SI")}
    )
