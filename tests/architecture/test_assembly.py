from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import pyomo.environ as pyo
import pytest

from pyspd.architecture import (
    AssemblyError,
    BuildContext,
    Formulation,
    FormulationRegistry,
    ModelAssembler,
    ModelComponent,
    PreprocessorStep,
    PricingEngine,
    ReportRenderer,
    ResultSchema,
    SolvePolicy,
)

FORMULATION = "vspd-v5.0.6"


class DomainComponent(ModelComponent):
    name = "domain"
    provides = frozenset({"nodes"})
    supported_formulations = frozenset({FORMULATION})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        context.model.domain = pyo.Block(concrete=True)
        context.model.domain.nodes = pyo.Set(initialize=("N1", "N2"), ordered=True)
        return {"nodes": context.model.domain.nodes}


class BalanceComponent(ModelComponent):
    name = "balance"
    requires = frozenset({"nodes"})
    provides = frozenset({"balance"})
    supported_formulations = frozenset({FORMULATION})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        context.model.balance = pyo.Block(concrete=True)
        context.model.balance.equation = pyo.Constraint(
            context.artifacts["nodes"], rule=lambda _block, _node: pyo.Constraint.Feasible
        )
        return {"balance": context.model.balance.equation}


class Policy(SolvePolicy):
    supported_formulations = frozenset({FORMULATION})

    def solve(self, built_model: Any) -> None:
        return None


class Pricing(PricingEngine):
    supported_formulations = frozenset({FORMULATION})

    def price(self, built_model: Any, solve_result: Any) -> None:
        return None


class Results(ResultSchema):
    supported_formulations = frozenset({FORMULATION})

    def collect(self, built_model: Any, solve_result: Any) -> None:
        return None


class Renderer(ReportRenderer):
    supported_formulations = frozenset({FORMULATION})

    def render(self, results: Any) -> None:
        return None


class Preprocess(PreprocessorStep):
    supported_formulations = frozenset({FORMULATION})

    def transform(self, case_data: Any) -> Any:
        return case_data


def formulation(*components: type[ModelComponent]) -> Formulation:
    return Formulation(
        formulation_id=FORMULATION,
        components=components,
        preprocessors=(Preprocess,),
        solve_policy=Policy,
        pricing_engine=Pricing,
        result_schema=Results,
        report_renderer=Renderer,
    )


def test_assembly_is_dependency_ordered_and_deterministic() -> None:
    selected = formulation(BalanceComponent, DomainComponent)

    first = ModelAssembler().assemble(selected, case_data=("immutable",))
    second = ModelAssembler().assemble(selected, case_data=("immutable",))

    assert first.build_order == second.build_order == ("domain", "balance")
    assert tuple(first.artifacts.values) == ("nodes", "balance")
    assert first.artifacts.owners == {"nodes": "domain", "balance": "balance"}


def test_missing_cycles_and_duplicate_ownership_fail_before_build() -> None:
    class Missing(ModelComponent):
        name = "missing"
        requires = frozenset({"nowhere"})
        supported_formulations = frozenset({FORMULATION})

        def build(self, context: BuildContext) -> Mapping[str, Any]:
            return {}

    class Left(ModelComponent):
        name = "left"
        requires = frozenset({"right_value"})
        provides = frozenset({"left_value"})
        supported_formulations = frozenset({FORMULATION})

        def build(self, context: BuildContext) -> Mapping[str, Any]:
            return {"left_value": object()}

    class Right(ModelComponent):
        name = "right"
        requires = frozenset({"left_value"})
        provides = frozenset({"right_value"})
        supported_formulations = frozenset({FORMULATION})

        def build(self, context: BuildContext) -> Mapping[str, Any]:
            return {"right_value": object()}

    class Duplicate(ModelComponent):
        name = "duplicate"
        provides = frozenset({"nodes"})
        supported_formulations = frozenset({FORMULATION})

        def build(self, context: BuildContext) -> Mapping[str, Any]:
            return {"nodes": object()}

    assembler = ModelAssembler()
    with pytest.raises(AssemblyError, match="missing provider"):
        assembler.assemble(formulation(Missing), ())
    with pytest.raises(AssemblyError, match="cycle"):
        assembler.assemble(formulation(Left, Right), ())
    with pytest.raises(AssemblyError, match="duplicate owner"):
        assembler.assemble(formulation(DomainComponent, Duplicate), ())


def test_formulation_selection_and_extension_versions_are_explicit() -> None:
    registry = FormulationRegistry()
    selected = formulation(DomainComponent)
    registry.register(selected)

    assert registry.resolve(FORMULATION) is selected
    with pytest.raises(AssemblyError, match="unknown formulation"):
        registry.resolve("date-selected-default")

    class WrongPolicy(Policy):
        supported_formulations: ClassVar[frozenset[str]] = frozenset({"vspd-v16"})

    incompatible = Formulation(
        formulation_id=FORMULATION,
        components=(DomainComponent,),
        preprocessors=(Preprocess,),
        solve_policy=WrongPolicy,
        pricing_engine=Pricing,
        result_schema=Results,
        report_renderer=Renderer,
    )
    with pytest.raises(AssemblyError, match="WrongPolicy.*vspd-v5.0.6"):
        ModelAssembler().assemble(incompatible, ())
