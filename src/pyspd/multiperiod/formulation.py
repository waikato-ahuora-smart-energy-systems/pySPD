"""Versioned build, solve, pricing, and result services for battery studies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import (
    BuiltModel,
    Formulation,
    ModelAssembler,
    PreprocessorStep,
    PricingEngine,
    ReportRenderer,
    ResultSchema,
    SolvePolicy,
)
from pyspd.multiperiod.components import (
    MultiPeriodBalanceComponent,
    MultiPeriodBatteryComponent,
    MultiPeriodDomainsComponent,
    MultiPeriodGenerationComponent,
    MultiPeriodObjectiveComponent,
)
from pyspd.multiperiod.data import (
    MULTIPERIOD_BATTERY_FORMULATION_ID,
    MultiPeriodCase,
)
from pyspd.solver import HighsBackend, SolverConfiguration, SolveResult

type Pair = tuple[str, str]
_SUPPORTED = frozenset({MULTIPERIOD_BATTERY_FORMULATION_ID})


class MultiPeriodIdentityPreprocessor(PreprocessorStep):
    supported_formulations = _SUPPORTED

    def transform(self, case_data: Any) -> MultiPeriodCase:
        if not isinstance(case_data, MultiPeriodCase):
            raise TypeError("battery formulation requires MultiPeriodCase")
        return case_data


class MultiPeriodSolvePolicy(SolvePolicy):
    supported_formulations = _SUPPORTED

    def solve(self, built_model: BuiltModel) -> SolveResult:
        return HighsBackend().solve(
            built_model.model,
            SolverConfiguration(
                {
                    "solver": "simplex",
                    "primal_feasibility_tolerance": 1e-9,
                    "dual_feasibility_tolerance": 1e-9,
                    "random_seed": 0,
                    "threads": 1,
                }
            ),
        )


class MultiPeriodPricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED

    def price(
        self, built_model: BuiltModel, solve_result: SolveResult
    ) -> Mapping[str, float]:
        if not solve_result.solution_loaded:
            raise ValueError("multi-period pricing requires a loaded optimal solution")
        balance = built_model.artifacts["energy_balance"]
        return MappingProxyType(
            {
                str(period): float(built_model.model.dual[balance[period]])
                for period in balance
            }
        )


@dataclass(frozen=True, slots=True)
class BatteryStudyResult:
    formulation_id: str
    case_id: str
    objective_nzd: float
    generation_mw: Mapping[Pair, float]
    charge_mw: Mapping[Pair, float]
    discharge_mw: Mapping[Pair, float]
    energy_mwh: Mapping[Pair, float]
    energy_prices: Mapping[str, float]
    balance_residual_mw: Mapping[str, float]
    storage_residual_mwh: Mapping[Pair, float]
    structural_signature: str

    def __post_init__(self) -> None:
        for name in (
            "generation_mw",
            "charge_mw",
            "discharge_mw",
            "energy_mwh",
            "energy_prices",
            "balance_residual_mw",
            "storage_residual_mwh",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


class MultiPeriodResultSchema(ResultSchema):
    supported_formulations = _SUPPORTED

    def collect(
        self, built_model: BuiltModel, solve_result: SolveResult
    ) -> BatteryStudyResult:
        if not solve_result.solution_loaded:
            raise ValueError("result collection requires a loaded optimal solution")
        data = built_model.case_data
        if not isinstance(data, MultiPeriodCase):
            raise TypeError("battery result collection requires MultiPeriodCase")
        generation = built_model.artifacts["generation"]
        charge = built_model.artifacts["battery_charge"]
        discharge = built_model.artifacts["battery_discharge"]
        energy = built_model.artifacts["battery_energy"]
        objective = built_model.artifacts["system_objective"]
        prices = MultiPeriodPricingEngine().price(built_model, solve_result)
        generation_values = _values(generation)
        charge_values = _values(charge)
        discharge_values = _values(discharge)
        energy_values = _values(energy)
        demand = {period.period_id: period.demand_mw for period in data.periods}
        duration = {period.period_id: period.duration_hours for period in data.periods}
        generator_ids = {
            period: tuple(
                offer.generator_id for offer in data.offers if offer.period_id == period
            )
            for period in data.period_ids
        }
        battery_by_id = {battery.battery_id: battery for battery in data.batteries}
        balance_residual = {
            period: (
                sum(
                    generation_values[(period, generator)]
                    for generator in generator_ids[period]
                )
                + sum(discharge_values[(period, battery)] for battery in battery_by_id)
                - demand[period]
                - sum(charge_values[(period, battery)] for battery in battery_by_id)
            )
            for period in data.period_ids
        }
        storage_residual: dict[Pair, float] = {}
        for index, period in enumerate(data.period_ids):
            for battery_id, battery in battery_by_id.items():
                previous = (
                    battery.initial_energy_mwh
                    if index == 0
                    else energy_values[(data.period_ids[index - 1], battery_id)]
                )
                storage_residual[(period, battery_id)] = (
                    energy_values[(period, battery_id)]
                    - previous
                    - duration[period]
                    * (
                        battery.charge_efficiency * charge_values[(period, battery_id)]
                        - discharge_values[(period, battery_id)]
                        / battery.discharge_efficiency
                    )
                )
        return BatteryStudyResult(
            formulation_id=built_model.formulation.formulation_id,
            case_id=data.case_id,
            objective_nzd=float(pyo.value(objective)),
            generation_mw=generation_values,
            charge_mw=charge_values,
            discharge_mw=discharge_values,
            energy_mwh=energy_values,
            energy_prices=prices,
            balance_residual_mw=balance_residual,
            storage_residual_mwh=storage_residual,
            structural_signature=built_model.structural_signature,
        )


class MultiPeriodReportRenderer(ReportRenderer):
    supported_formulations = _SUPPORTED

    def render(self, results: Any) -> Mapping[str, Any]:
        if not isinstance(results, BatteryStudyResult):
            raise TypeError("battery report rendering requires BatteryStudyResult")
        payload: dict[str, Any] = {
            "formulation_id": results.formulation_id,
            "case_id": results.case_id,
            "objective_nzd": results.objective_nzd,
            "energy_prices": dict(results.energy_prices),
            "balance_residual_mw": dict(results.balance_residual_mw),
            "structural_signature": results.structural_signature,
        }
        for name in (
            "generation_mw",
            "charge_mw",
            "discharge_mw",
            "energy_mwh",
            "storage_residual_mwh",
        ):
            values = getattr(results, name)
            payload[name] = {"|".join(key): value for key, value in values.items()}
        return MappingProxyType(payload)


def build_battery_formulation() -> Formulation:
    return Formulation(
        formulation_id=MULTIPERIOD_BATTERY_FORMULATION_ID,
        components=(
            MultiPeriodDomainsComponent,
            MultiPeriodBatteryComponent,
            MultiPeriodGenerationComponent,
            MultiPeriodBalanceComponent,
            MultiPeriodObjectiveComponent,
        ),
        preprocessors=(MultiPeriodIdentityPreprocessor,),
        solve_policy=MultiPeriodSolvePolicy,
        pricing_engine=MultiPeriodPricingEngine,
        result_schema=MultiPeriodResultSchema,
        report_renderer=MultiPeriodReportRenderer,
    )


class BatteryStudyRunner:
    """Compose and solve the explicitly separate battery research formulation."""

    def __init__(self, *, formulation: Formulation | None = None) -> None:
        self.formulation = formulation or build_battery_formulation()
        if self.formulation.formulation_id != MULTIPERIOD_BATTERY_FORMULATION_ID:
            raise ValueError("BatteryStudyRunner requires the battery formulation")

    def build(self, case_data: MultiPeriodCase) -> BuiltModel:
        return ModelAssembler().assemble(self.formulation, case_data)

    def run(self, case_data: MultiPeriodCase) -> BatteryStudyResult:
        built = self.build(case_data)
        solve = self.formulation.solve_policy().solve(built)
        result = self.formulation.result_schema().collect(built, solve)
        if not isinstance(result, BatteryStudyResult):
            raise TypeError("battery formulation returned an unexpected result type")
        return result


def _values(component: Any) -> dict[Pair, float]:
    return {tuple(index): float(pyo.value(component[index])) for index in component}
