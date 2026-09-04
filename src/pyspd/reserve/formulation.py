"""Full Gate 7 reserve formulation and requalified MIP-pricing policy."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
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
from pyspd.hvdc.formulation import (
    HvdcSolveOutcome,
    HvdcSolvePolicy,
    PricingCanonicalizationAudit,
    SolutionSnapshot,
    pricing_model_belongs_to_request,
)
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
from pyspd.reserve.data import RESERVE_BREAKPOINTS, RESERVE_FORMULATION_ID, ReserveCase
from pyspd.solver import SolveResult, SolverExecutionError

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

    def solve(self, built_model: BuiltModel) -> HvdcSolveOutcome:
        outcome = super().solve(built_model)
        result, snapshot, audit = ReserveKinkCanonicalizer().canonicalize(
            outcome.pricing_model,
            outcome.pricing_lp,
            outcome.pricing_snapshot,
            lambda pricing: self._solve_pricing(pricing),
        )
        return replace(
            outcome,
            pricing_lp=result,
            pricing_snapshot=snapshot,
            pricing_canonicalization=audit,
        )

    def _formulation(self) -> Formulation:
        return reserve_formulation()


class ReserveKinkCanonicalizer:
    """Select an adjacent reserve-loss breakpoint when economically immaterial.

    Historical CPLEX can terminate on the exact endpoint of a reserve-loss
    segment while a tighter fixed-RMIP solve moves a very small distance onto
    the adjacent segment.  The endpoint changes duals and reserve-sharing
    allocation despite having no material economic effect.  A candidate is
    considered only when one convex weight is already dominant, and is kept
    only when the secondary solve loses no more than the explicit objective
    budget.
    """

    policy = "dominant-reserve-loss-breakpoint-v1"

    def __init__(
        self,
        *,
        minimum_dominant_weight: float = 0.999,
        objective_loss_budget: float = 1e-3,
        equality_tolerance: float = 1e-9,
    ) -> None:
        if not 0.5 < minimum_dominant_weight < 1.0:
            raise ValueError("minimum_dominant_weight must lie in (0.5, 1)")
        if objective_loss_budget < 0.0 or equality_tolerance < 0.0:
            raise ValueError("canonicalization tolerances cannot be negative")
        self.minimum_dominant_weight = float(minimum_dominant_weight)
        self.objective_loss_budget = float(objective_loss_budget)
        self.equality_tolerance = float(equality_tolerance)

    def canonicalize(
        self,
        built: BuiltModel,
        baseline_result: SolveResult,
        baseline_snapshot: SolutionSnapshot,
        solve: Callable[[BuiltModel], SolveResult],
    ) -> tuple[SolveResult, SolutionSnapshot, PricingCanonicalizationAudit]:
        candidates = self._candidate_targets(built)
        if not candidates:
            audit = PricingCanonicalizationAudit(
                self.policy,
                {},
                {},
                baseline_snapshot.objective,
                baseline_snapshot.objective,
                0.0,
                self.objective_loss_budget,
            )
            return baseline_result, baseline_snapshot, audit

        model = built.model
        overlay_name = "ReserveLossBreakpointCanonicalization"
        if model.component(overlay_name) is not None:
            raise ValueError("reserve-loss canonicalization overlay already exists")
        baseline_values = tuple(
            (variable, float(value))
            for variable in model.component_data_objects(pyo.Var, active=True)
            if (value := pyo.value(variable, exception=False)) is not None
        )
        baseline_duals = tuple(model.dual.items())
        overlay = pyo.ConstraintList()
        model.add_component(overlay_name, overlay)
        reserve_sent = built.artifacts["hvdc_reserve_sent"]
        for key, target in candidates.items():
            overlay.add(reserve_sent[key] == target)
        model.dual.clear()
        try:
            candidate_result = solve(built)
            candidate_snapshot = SolutionSnapshot.capture(built)
            objective = next(model.component_data_objects(pyo.Objective, active=True))
            loss = self._objective_loss(
                objective.sense,
                baseline_snapshot.objective,
                candidate_snapshot.objective,
            )
        except SolverExecutionError:
            candidate_result = None
            candidate_snapshot = None
            loss = float("inf")

        accepted = loss <= self.objective_loss_budget
        if accepted:
            assert candidate_result is not None
            assert candidate_snapshot is not None
            audit = PricingCanonicalizationAudit(
                self.policy,
                self._named(candidates),
                self._named(candidates),
                baseline_snapshot.objective,
                candidate_snapshot.objective,
                loss,
                self.objective_loss_budget,
            )
            return candidate_result, candidate_snapshot, audit

        model.del_component(overlay_name)
        for variable, value in baseline_values:
            variable.set_value(value, skip_validation=True)
        model.dual.clear()
        for constraint, value in baseline_duals:
            model.dual[constraint] = value
        audit = PricingCanonicalizationAudit(
            self.policy,
            self._named(candidates),
            {},
            baseline_snapshot.objective,
            baseline_snapshot.objective,
            loss,
            self.objective_loss_budget,
        )
        return baseline_result, baseline_snapshot, audit

    def _candidate_targets(self, built: BuiltModel) -> dict[Key, float]:
        case = built.case_data
        if not isinstance(case, ReserveCase) or case.reserve is None:
            raise TypeError("reserve kink canonicalization requires ReserveCase")
        lambdas = built.artifacts["lambda_hvdc_reserve"]
        reserve_sent = built.artifacts["hvdc_reserve_sent"]
        candidates: dict[Key, float] = {}
        directed = sorted({tuple(index[:-1]) for index in lambdas})
        for key in directed:
            dominant = max(
                (
                    (float(pyo.value(lambdas[*key, breakpoint])), breakpoint)
                    for breakpoint in RESERVE_BREAKPOINTS
                ),
                key=lambda item: item[0],
            )
            weight, breakpoint = dominant
            if weight < self.minimum_dominant_weight or weight >= 1.0:
                continue
            target = float(
                case.reserve.reserve_breakpoint_flow[*key[:3], breakpoint]
            )
            current = float(pyo.value(reserve_sent[key]))
            if abs(current - target) > self.equality_tolerance:
                candidates[key] = target
        return candidates

    @staticmethod
    def _objective_loss(sense: Any, baseline: float, candidate: float) -> float:
        signed = baseline - candidate if sense is pyo.maximize else candidate - baseline
        return max(0.0, signed)

    @staticmethod
    def _named(values: Mapping[Key, float]) -> dict[str, float]:
        return {"|".join(key): value for key, value in values.items()}


class ReservePricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED

    def price(
        self, built_model: BuiltModel, solve_result: HvdcSolveOutcome
    ) -> ReservePrices:
        if not pricing_model_belongs_to_request(
            built_model, solve_result.primary_model
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
