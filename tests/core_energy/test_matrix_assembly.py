from __future__ import annotations

from dataclasses import replace

import pyomo.environ as pyo

from pyspd.architecture import (
    BuildContext,
    ModelAssembler,
    ModelComponent,
    ReportRenderer,
    ResultSchema,
    SolvePolicy,
)
from pyspd.core_energy import CORE_ENERGY_FORMULATION_ID, core_energy_formulation
from pyspd.core_energy.matrix import canonical_linear_matrix
from tests.core_energy.conftest import make_core_case


def test_canonical_matrix_has_exact_bounds_coefficients_and_stable_hash() -> None:
    data = make_core_case(load=10.0, offers=(("GEN", 20.0, 7.0),))
    assembler = ModelAssembler()
    first = assembler.assemble(core_energy_formulation(), data)
    second = assembler.assemble(core_energy_formulation(), data)
    left = canonical_linear_matrix(first.model)
    right = canonical_linear_matrix(second.model)
    assert left.logical_sha256 == right.logical_sha256
    assert first.structural_signature == second.structural_signature
    assert first.model is not second.model
    generation_block = next(
        item for item in left.variables if "GenerationBlock[C1,T1,GEN" in item.name
    )
    assert (generation_block.lower, generation_block.upper, generation_block.objective) == (
        0.0,
        20.0,
        0.0,
    )
    definition = next(
        row for row in left.rows if "GenerationOfferDefinition" in row.name
    )
    assert sorted(value for _name, value in definition.coefficients) == [-1.0, 1.0]
    assert definition.lower == definition.upper == 0.0
    cost_definition = next(row for row in left.rows if "SystemCostDefinition" in row.name)
    assert -7.0 in {value for _name, value in cost_definition.coefficients}


class SyntheticComponent(ModelComponent):
    name = "synthetic_extension"
    supported_formulations = frozenset({CORE_ENERGY_FORMULATION_ID})
    requires = frozenset({"objective"})
    provides = frozenset({"synthetic_marker"})

    def build(self, context: BuildContext):
        context.model.SyntheticMarker = pyo.Expression(expr=1.0)
        return {"synthetic_marker": context.model.SyntheticMarker}


class SyntheticPolicy(SolvePolicy):
    supported_formulations = frozenset({CORE_ENERGY_FORMULATION_ID})

    def solve(self, built_model):
        return built_model.artifacts["synthetic_marker"]


class SyntheticSchema(ResultSchema):
    supported_formulations = frozenset({CORE_ENERGY_FORMULATION_ID})

    def collect(self, built_model, solve_result):
        return pyo.value(solve_result)


class SyntheticRenderer(ReportRenderer):
    supported_formulations = frozenset({CORE_ENERGY_FORMULATION_ID})

    def render(self, results):
        return {"synthetic": results}


def test_public_extensions_replace_without_assembler_changes() -> None:
    base = core_energy_formulation()
    extended = replace(
        base,
        components=(*base.components, SyntheticComponent),
        solve_policy=SyntheticPolicy,
        result_schema=SyntheticSchema,
        report_renderer=SyntheticRenderer,
    )
    built = ModelAssembler().assemble(extended, make_core_case(load=0.0))
    solved = extended.solve_policy().solve(built)
    results = extended.result_schema().collect(built, solved)
    assert extended.report_renderer().render(results) == {"synthetic": 1.0}
    assert built.artifacts.owners["synthetic_marker"] == "synthetic_extension"
