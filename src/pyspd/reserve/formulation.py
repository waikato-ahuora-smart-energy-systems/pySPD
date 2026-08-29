"""Full Gate 7 reserve formulation and requalified MIP-pricing policy."""

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
)
from pyspd.contracts import CaseData
from pyspd.core_energy.components import (
    CoreDomainsComponent,
    DemandBidsComponent,
    EnergyOffersComponent,
    EnergyScarcityComponent,
    GenerationRampingComponent,
)
from pyspd.hvdc.components import (
    DiscreteDemandComponent,
    HVDCACNetworkComponent,
    HVDCDomainsComponent,
    HVDCTransmissionComponent,
)
from pyspd.hvdc.formulation import HvdcSolveOutcome, HvdcSolvePolicy
from pyspd.network.components import NetworkDomainsComponent
from pyspd.network.formulation import NetworkPrices, NetworkPricingEngine
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor
from pyspd.reserve.components import (
    IslandReserveComponent,
    ReserveDomainsComponent,
    ReserveEconomicsComponent,
    ReserveOfferComponent,
    ReserveRequirementComponent,
    ReserveRiskComponent,
    ReserveScarcityComponent,
    ReserveSecurityComponent,
    ReserveSharingComponent,
)
from pyspd.reserve.data import RESERVE_FORMULATION_ID, ReserveCase

type Key = tuple[str, ...]

_SUPPORTED = frozenset({RESERVE_FORMULATION_ID})


class ReservePreprocessor(PreprocessorStep):
    supported_formulations = _SUPPORTED

    def transform(self, case_data: Any) -> ReserveCase:
        if isinstance(case_data, ReserveCase):
            return case_data
        if not isinstance(case_data, CaseData):
            raise TypeError("reserve preprocessing requires CaseData")
        result = Vspd506Preprocessor(
            PreprocessingSettings(apply_rtd_load_reconstruction=True)
        ).transform(case_data)
        return ReserveCase.from_sources(result, case_data)


class ReserveSolvePolicy(HvdcSolvePolicy):
    supported_formulations = _SUPPORTED

    def _formulation(self) -> Formulation:
        return reserve_formulation()


class ReservePricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED

    def price(
        self, built_model: BuiltModel, solve_result: HvdcSolveOutcome
    ) -> ReservePrices:
        if solve_result.primary_model is not built_model and (
            solve_result.primary_model.case_data != built_model.case_data
        ):
            raise ValueError("pricing outcome does not belong to the requested case")
        pricing = solve_result.pricing_model
        energy = NetworkPricingEngine().price(pricing, solve_result.pricing_lp)
        constraints = pricing.artifacts["island_reserve_definition"]
        reserve = {
            tuple(index): float(pricing.model.dual[constraints[index]])
            for index in constraints
        }
        return ReservePrices(energy, reserve, reserve)


@dataclass(frozen=True, slots=True)
class ReservePrices:
    energy: NetworkPrices
    reserve: Mapping[Key, float]
    raw_reserve_duals: Mapping[Key, float]
    unit: str = "NZD/MWh"
    convention: str = "objective sensitivity to +1 MW available island reserve"

    def __post_init__(self) -> None:
        object.__setattr__(self, "reserve", MappingProxyType(dict(self.reserve)))
        object.__setattr__(
            self,
            "raw_reserve_duals",
            MappingProxyType(dict(self.raw_reserve_duals)),
        )


@dataclass(frozen=True, slots=True)
class ReserveResults:
    generation: Mapping[Key, float]
    energy_purchase: Mapping[Key, float]
    reserve: Mapping[Key, float]
    island_reserve: Mapping[Key, float]
    island_risk: Mapping[Key, float]
    shared_reserve: Mapping[Key, float]
    reserve_shortfall: Mapping[Key, float]
    node_prices: Mapping[Key, float]
    reserve_prices: Mapping[Key, float]
    primary_objective: float
    pricing_objective: float
    fixed_discrete: Mapping[str, float]

    def __post_init__(self) -> None:
        for name in (
            "generation",
            "energy_purchase",
            "reserve",
            "island_reserve",
            "island_risk",
            "shared_reserve",
            "reserve_shortfall",
            "node_prices",
            "reserve_prices",
            "fixed_discrete",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


class ReserveResultSchema(ResultSchema):
    supported_formulations = _SUPPORTED

    def collect(
        self, built_model: BuiltModel, solve_result: HvdcSolveOutcome
    ) -> ReserveResults:
        primary = solve_result.primary_model
        prices = ReservePricingEngine().price(built_model, solve_result)
        return ReserveResults(
            _values(primary.artifacts["generation"]),
            _values(primary.artifacts["purchase"]),
            _values(primary.artifacts["reserve"]),
            _values(primary.artifacts["island_reserve"]),
            _values(primary.artifacts["island_risk"]),
            _values(primary.artifacts["shared_reserve"]),
            _values(primary.artifacts["reserve_shortfall"]),
            prices.energy.node,
            prices.reserve,
            solve_result.primary_snapshot.objective,
            solve_result.pricing_snapshot.objective,
            solve_result.fixed_discrete,
        )


class ReserveReportRenderer(ReportRenderer):
    supported_formulations = _SUPPORTED

    def render(self, results: Any) -> Mapping[str, Any]:
        if not isinstance(results, ReserveResults):
            raise TypeError("renderer requires ReserveResults")
        return MappingProxyType(
            {
                "generation_mw": dict(results.generation),
                "energy_purchase_mw": dict(results.energy_purchase),
                "reserve_mw": dict(results.reserve),
                "island_reserve_mw": dict(results.island_reserve),
                "island_risk_mw": dict(results.island_risk),
                "shared_reserve_mw": dict(results.shared_reserve),
                "reserve_shortfall_mw": dict(results.reserve_shortfall),
                "node_prices_nzd_per_mwh": dict(results.node_prices),
                "reserve_prices_nzd_per_mwh": dict(results.reserve_prices),
                "primary_objective_nzd": results.primary_objective,
                "pricing_objective_nzd": results.pricing_objective,
                "fixed_discrete": dict(results.fixed_discrete),
            }
        )


def reserve_formulation(*, preprocess: bool = False) -> Formulation:
    return Formulation(
        formulation_id=RESERVE_FORMULATION_ID,
        components=(
            CoreDomainsComponent,
            EnergyOffersComponent,
            DemandBidsComponent,
            EnergyScarcityComponent,
            NetworkDomainsComponent,
            HVDCDomainsComponent,
            HVDCTransmissionComponent,
            DiscreteDemandComponent,
            HVDCACNetworkComponent,
            GenerationRampingComponent,
            ReserveDomainsComponent,
            ReserveOfferComponent,
            IslandReserveComponent,
            ReserveScarcityComponent,
            ReserveSharingComponent,
            ReserveRiskComponent,
            ReserveRequirementComponent,
            ReserveSecurityComponent,
            ReserveEconomicsComponent,
        ),
        preprocessors=(ReservePreprocessor,) if preprocess else (),
        solve_policy=ReserveSolvePolicy,
        pricing_engine=ReservePricingEngine,
        result_schema=ReserveResultSchema,
        report_renderer=ReserveReportRenderer,
    )


def _values(component: Any) -> dict[Key, float]:
    return {
        tuple(index): float(pyo.value(component[index], exception=False) or 0.0)
        for index in component
    }
