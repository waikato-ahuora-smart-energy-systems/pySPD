"""Class composition, solve, price, result, and report policy for SPD v16."""

from __future__ import annotations

from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuiltModel, Formulation, PricingEngine, ResultSchema
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
from pyspd.hvdc.formulation import HvdcSolveOutcome
from pyspd.network.components import NetworkDomainsComponent
from pyspd.network.formulation import NetworkPricingEngine
from pyspd.reserve.components import (
    IslandReserveComponent,
    ReserveDomainsComponent,
    ReserveOfferComponent,
    ReserveScarcityComponent,
    ReserveSecurityComponent,
    ReserveSharingComponent,
)
from pyspd.reserve.formulation import (
    ReservePrices,
    ReserveReportRenderer,
    ReserveResults,
    ReserveSolvePolicy,
)
from pyspd.v16.compatibility import SPD16_FORMULATION_ID
from pyspd.v16.components import (
    Spd16BatteryModeComponent,
    Spd16ReserveEconomicsComponent,
    Spd16ReserveRequirementComponent,
    Spd16ReserveRiskComponent,
    Spd16TieBreakComponent,
)
from pyspd.v16.preprocess import Spd16ModelPreprocessor

type Key = tuple[str, ...]

_SUPPORTED = frozenset({SPD16_FORMULATION_ID})


class Spd16SolvePolicy(ReserveSolvePolicy):
    supported_formulations = _SUPPORTED

    def _formulation(self) -> Formulation:
        return spd16_formulation()


class Spd16PricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED
    zero_tolerance = 1e-9

    @staticmethod
    def select_reserve_price(
        *,
        island_reserve_mw: float,
        definition_dual: float,
        requirement_duals: tuple[float, ...],
        tolerance: float = 1e-9,
    ) -> float:
        if abs(island_reserve_mw) <= tolerance:
            return float(sum(requirement_duals))
        return float(definition_dual)

    def price(
        self, built_model: BuiltModel, solve_result: HvdcSolveOutcome
    ) -> ReservePrices:
        if solve_result.primary_model is not built_model and (
            solve_result.primary_model.case_data != built_model.case_data
        ):
            raise ValueError("pricing outcome does not belong to the requested case")
        pricing = solve_result.pricing_model
        energy = NetworkPricingEngine().price(pricing, solve_result.pricing_lp)
        definitions = pricing.artifacts["island_reserve_definition"]
        requirements = pricing.artifacts["reserve_requirement"]
        island_reserve = pricing.artifacts["island_reserve"]
        raw = {
            tuple(index): float(pricing.model.dual[definitions[index]])
            for index in definitions
        }
        reserve: dict[Key, float] = {}
        for index in definitions:
            key = tuple(index)
            requirement_duals = tuple(
                float(pricing.model.dual[requirements[item]])
                for item in requirements
                if tuple(item)[:4] == key
            )
            reserve[key] = self.select_reserve_price(
                island_reserve_mw=float(pyo.value(island_reserve[index])),
                definition_dual=raw[key],
                requirement_duals=requirement_duals,
                tolerance=self.zero_tolerance,
            )
        return ReservePrices(energy, reserve, raw)


class Spd16ResultSchema(ResultSchema):
    supported_formulations = _SUPPORTED

    def collect(
        self, built_model: BuiltModel, solve_result: HvdcSolveOutcome
    ) -> ReserveResults:
        primary = solve_result.primary_model
        prices = Spd16PricingEngine().price(built_model, solve_result)
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


class Spd16ReportRenderer(ReserveReportRenderer):
    supported_formulations = _SUPPORTED


def spd16_formulation(*, preprocess: bool = False) -> Formulation:
    return Formulation(
        formulation_id=SPD16_FORMULATION_ID,
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
            Spd16ReserveRiskComponent,
            Spd16ReserveRequirementComponent,
            Spd16BatteryModeComponent,
            Spd16TieBreakComponent,
            ReserveSecurityComponent,
            Spd16ReserveEconomicsComponent,
        ),
        preprocessors=(Spd16ModelPreprocessor,) if preprocess else (),
        solve_policy=Spd16SolvePolicy,
        pricing_engine=Spd16PricingEngine,
        result_schema=Spd16ResultSchema,
        report_renderer=Spd16ReportRenderer,
    )


def _values(component: Any) -> dict[Key, float]:
    return {
        tuple(index): float(pyo.value(component[index], exception=False) or 0.0)
        for index in component
    }
