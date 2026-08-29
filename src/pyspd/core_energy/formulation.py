"""Public Gate 4 formulation profile and extension implementations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import (
    BuiltModel,
    Formulation,
    PreprocessorStep,
    PricingEngine,
    ReportRenderer,
    ResultSchema,
    SolvePolicy,
)
from pyspd.contracts import CaseData
from pyspd.core_energy.components import (
    CoreDomainsComponent,
    CoreEconomicsComponent,
    DemandBidsComponent,
    EnergyBalanceComponent,
    EnergyOffersComponent,
    EnergyScarcityComponent,
    GenerationRampingComponent,
)
from pyspd.core_energy.data import CORE_ENERGY_FORMULATION_ID, CoreEnergyCase, Region
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor
from pyspd.solver import HighsBackend, SolverConfiguration, SolveResult

_SUPPORTED = frozenset({CORE_ENERGY_FORMULATION_ID})


class CoreEnergyPreprocessor(PreprocessorStep):
    """Run the qualified Gate 3 profile and project its immutable artifacts."""

    supported_formulations = _SUPPORTED

    def transform(self, case_data: Any) -> CoreEnergyCase:
        if isinstance(case_data, CoreEnergyCase):
            return case_data
        if not isinstance(case_data, CaseData):
            raise TypeError("core-energy preprocessing requires CaseData")
        result = Vspd506Preprocessor(
            PreprocessingSettings(apply_rtd_load_reconstruction=True)
        ).transform(case_data)
        return CoreEnergyCase.from_preprocessing(result)


class CoreEnergySolvePolicy(SolvePolicy):
    supported_formulations = _SUPPORTED

    def solve(self, built_model: BuiltModel) -> SolveResult:
        return HighsBackend().solve(
            built_model.model,
            SolverConfiguration(
                {
                    "solver": "simplex",
                    "primal_feasibility_tolerance": 1e-8,
                    "dual_feasibility_tolerance": 1e-8,
                    "random_seed": 0,
                    "threads": 1,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class CoreEnergyPrices:
    values: Mapping[Region, float]
    raw_duals: Mapping[Region, float]
    unit: str = "NZD/MWh"
    convention: str = "negative objective sensitivity to +1 MW required load"

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "raw_duals", MappingProxyType(dict(self.raw_duals)))


class CoreEnergyPricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED

    def price(
        self, built_model: BuiltModel, solve_result: SolveResult
    ) -> CoreEnergyPrices:
        if not solve_result.solution_loaded:
            raise ValueError("pricing requires an optimal loaded LP solution")
        constraints = built_model.artifacts["energy_balance"]
        raw = {
            tuple(index): float(built_model.model.dual[constraints[index]])
            for index in constraints
        }
        # With supply on the left and demand on the right of a maximization
        # equality, Pyomo/HiGHS returns d(objective)/d(required-load). Market
        # price is the cost of one additional MW, hence the negative sign.
        return CoreEnergyPrices(
            values={region: -dual for region, dual in raw.items()}, raw_duals=raw
        )


@dataclass(frozen=True, slots=True)
class CoreEnergyResults:
    generation: Mapping[tuple[str, ...], float]
    purchases: Mapping[tuple[str, ...], float]
    deficit: Mapping[Region, float]
    surplus: Mapping[Region, float]
    objective_components: Mapping[str, float]

    def __post_init__(self) -> None:
        for name in (
            "generation",
            "purchases",
            "deficit",
            "surplus",
            "objective_components",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


def _values(component: Any) -> dict[tuple[str, ...], float]:
    output: dict[tuple[str, ...], float] = {}
    for index in component:
        value = pyo.value(component[index], exception=False)
        output[tuple(index)] = 0.0 if value is None else float(value)
    return output


class CoreEnergyResultSchema(ResultSchema):
    supported_formulations = _SUPPORTED

    def collect(
        self, built_model: BuiltModel, solve_result: SolveResult
    ) -> CoreEnergyResults:
        if not solve_result.solution_loaded:
            raise ValueError("result collection requires a loaded solution")
        artifacts = built_model.artifacts
        return CoreEnergyResults(
            generation=_values(artifacts["generation"]),
            purchases=_values(artifacts["purchase"]),
            deficit=_values(artifacts["balance_deficit"]),
            surplus=_values(artifacts["balance_surplus"]),
            objective_components={
                name: float(pyo.value(artifacts[name]))
                for name in (
                    "system_cost",
                    "system_benefit",
                    "balance_penalty",
                    "ramp_penalty",
                    "movement_cost",
                    "scarcity_cost",
                    "system_penalty",
                    "net_benefit",
                )
            },
        )


class CoreEnergyReportRenderer(ReportRenderer):
    supported_formulations = _SUPPORTED

    def render(self, results: Any) -> Mapping[str, Any]:
        if not isinstance(results, CoreEnergyResults):
            raise TypeError("renderer requires CoreEnergyResults")
        return MappingProxyType(
            {
                "generation_mw": dict(results.generation),
                "purchase_mw": dict(results.purchases),
                "deficit_mw": dict(results.deficit),
                "surplus_mw": dict(results.surplus),
                "objective_nzd": dict(results.objective_components),
            }
        )


def core_energy_formulation(*, preprocess: bool = False) -> Formulation:
    """Return the modular public profile for direct or Gate-3-derived data."""

    return Formulation(
        formulation_id=CORE_ENERGY_FORMULATION_ID,
        components=(
            CoreDomainsComponent,
            EnergyOffersComponent,
            DemandBidsComponent,
            EnergyScarcityComponent,
            EnergyBalanceComponent,
            GenerationRampingComponent,
            CoreEconomicsComponent,
        ),
        preprocessors=(CoreEnergyPreprocessor,) if preprocess else (),
        solve_policy=CoreEnergySolvePolicy,
        pricing_engine=CoreEnergyPricingEngine,
        result_schema=CoreEnergyResultSchema,
        report_renderer=CoreEnergyReportRenderer,
    )
