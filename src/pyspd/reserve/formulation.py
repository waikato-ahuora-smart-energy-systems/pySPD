"""Full Gate 7 reserve formulation and requalified MIP-pricing policy."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
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
from pyspd.reserve.data import (
    RESERVE_BREAKPOINTS,
    RESERVE_CLASSES,
    RESERVE_FORMULATION_ID,
    ReserveCase,
)
from pyspd.solver import (
    HighsBackend,
    SolverConfiguration,
    SolveResult,
    SolverExecutionError,
)

type Key = tuple[str, ...]
type CanonicalTarget = tuple[str, Key]

_RESERVE_TOTAL_TARGET = "reserve_total"

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
    """Select deterministic reserve boundaries when economically immaterial.

    Historical CPLEX can terminate on the exact endpoint of a reserve-loss
    segment while a tighter fixed-RMIP solve moves a very small distance onto
    the adjacent segment.  The same effect occurs at the round-power zone exit.
    These endpoints change duals and reserve-sharing allocation despite having
    no material economic effect.  Candidates are tightly bounded in weight or
    MW distance and are kept only when the secondary solve loses no more than
    the applicable explicit objective budget.

    Zero-priced offered reserve can also be left above the binding island
    reserve quantity because the excess has no objective coefficient.  Such a
    surplus is removed by equating total offered reserve to island reserve and
    accepting the re-solve only within its stricter objective budget.
    """

    policy = "reserve-boundary-and-zero-price-surplus-v3"

    def __init__(
        self,
        *,
        minimum_dominant_weight: float = 0.999,
        objective_loss_budget: float = 1e-3,
        maximum_round_power_distance_mw: float = 1.0,
        round_power_objective_loss_budget: float = 1e-2,
        surplus_objective_loss_budget: float = 1e-7,
        surplus_tolerance_mw: float = 1e-6,
        zero_price_tolerance: float = 1e-9,
        equality_tolerance: float = 1e-9,
    ) -> None:
        if not 0.5 < minimum_dominant_weight < 1.0:
            raise ValueError("minimum_dominant_weight must lie in (0.5, 1)")
        if (
            objective_loss_budget < 0.0
            or maximum_round_power_distance_mw < 0.0
            or round_power_objective_loss_budget < 0.0
            or surplus_objective_loss_budget < 0.0
            or surplus_tolerance_mw < 0.0
            or zero_price_tolerance < 0.0
            or equality_tolerance < 0.0
        ):
            raise ValueError("canonicalization tolerances cannot be negative")
        self.minimum_dominant_weight = float(minimum_dominant_weight)
        self.objective_loss_budget = float(objective_loss_budget)
        self.maximum_round_power_distance_mw = float(
            maximum_round_power_distance_mw
        )
        self.round_power_objective_loss_budget = float(
            round_power_objective_loss_budget
        )
        self.surplus_objective_loss_budget = float(surplus_objective_loss_budget)
        self.surplus_tolerance_mw = float(surplus_tolerance_mw)
        self.zero_price_tolerance = float(zero_price_tolerance)
        self.equality_tolerance = float(equality_tolerance)

    def canonicalize(
        self,
        built: BuiltModel,
        baseline_result: SolveResult,
        baseline_snapshot: SolutionSnapshot,
        solve: Callable[[BuiltModel], SolveResult],
    ) -> tuple[SolveResult, SolutionSnapshot, PricingCanonicalizationAudit]:
        candidates = self._candidate_targets(built)
        allowed_loss = self._allowed_objective_loss(candidates)
        if not candidates:
            audit = PricingCanonicalizationAudit(
                self.policy,
                {},
                {},
                baseline_snapshot.objective,
                baseline_snapshot.objective,
                0.0,
                allowed_loss,
            )
            return baseline_result, baseline_snapshot, audit

        model = built.model
        overlay_name = "ReserveBoundaryCanonicalization"
        if model.component(overlay_name) is not None:
            raise ValueError("reserve boundary canonicalization overlay already exists")
        baseline_values = tuple(
            (variable, float(value))
            for variable in model.component_data_objects(pyo.Var, active=True)
            if (value := pyo.value(variable, exception=False)) is not None
        )
        baseline_duals = tuple(model.dual.items())
        overlay = pyo.ConstraintList()
        model.add_component(overlay_name, overlay)
        for (artifact_name, key), target in candidates.items():
            if artifact_name == _RESERVE_TOTAL_TARGET:
                overlay.add(built.artifacts["island_reserve"][key] == target)
                overlay.add(self._reserve_total_expression(built, key) == 0.0)
            else:
                overlay.add(built.artifacts[artifact_name][key] == target)
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

        accepted = loss <= allowed_loss
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
                allowed_loss,
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
            allowed_loss,
        )
        return baseline_result, baseline_snapshot, audit

    def _candidate_targets(self, built: BuiltModel) -> dict[CanonicalTarget, float]:
        candidates: dict[CanonicalTarget, float] = {
            ("hvdc_reserve_sent", key): target
            for key, target in self._reserve_loss_targets(built).items()
        }
        candidates.update(self._round_power_targets(built))
        candidates.update(
            {
                (_RESERVE_TOTAL_TARGET, key): target
                for key, target in self._zero_price_surplus_targets(built).items()
            }
        )
        return candidates

    def _zero_price_surplus_targets(self, built: BuiltModel) -> dict[Key, float]:
        case = built.case_data
        if not isinstance(case, ReserveCase) or case.reserve is None:
            raise TypeError("reserve surplus canonicalization requires ReserveCase")
        island_reserve = built.artifacts["island_reserve"]
        definitions = built.artifacts["island_reserve_definition"]
        targets: dict[Key, float] = {}
        for key in island_reserve:
            constraint = definitions[key]
            price = built.model.dual.get(constraint, float("nan"))
            if not math.isfinite(float(price)) or abs(float(price)) > self.zero_price_tolerance:
                continue
            level = float(pyo.value(island_reserve[key]))
            required = self._published_reserve_requirement(built, tuple(key))
            total = level + float(
                pyo.value(self._reserve_total_expression(built, key))
            )
            if max(level, total) - required > self.surplus_tolerance_mw:
                targets[tuple(key)] = required
        return targets

    @staticmethod
    def _published_reserve_requirement(built: BuiltModel, key: Key) -> float:
        """Recompute the requirement used by the governed reserve reports."""

        case = built.case_data
        if not isinstance(case, ReserveCase) or case.reserve is None:
            raise TypeError("reserve surplus canonicalization requires ReserveCase")
        ca, dt, island, reserve_class = key
        prefix = (ca, dt, island)
        effective = built.artifacts["reserve_share_effective"]
        candidates = [0.0]
        for name in ("generator_island_risk", "group_island_risk"):
            for risk_key, risk in built.artifacts[name].items():
                if risk_key[:3] != prefix or risk_key[-2] != reserve_class:
                    continue
                effective_key = (*prefix, reserve_class, risk_key[-1])
                candidates.append(
                    float(pyo.value(risk))
                    + (
                        float(pyo.value(effective[effective_key]))
                        if effective_key in effective
                        else 0.0
                    )
                )
        for risk_key, risk in built.artifacts["island_risk"].items():
            if risk_key[:4] != key:
                continue
            if risk_key[4] in case.reserve.manual_risks:
                candidates.append(
                    float(pyo.value(risk))
                    + (
                        float(pyo.value(effective[risk_key]))
                        if risk_key in effective
                        else 0.0
                    )
                )
            elif risk_key[4] in case.reserve.hvdc_risks:
                candidates.append(float(pyo.value(risk)))
        for name in ("hvdc_generator_island_risk", "hvdc_manual_island_risk"):
            for risk_key, risk in built.artifacts[name].items():
                if risk_key[:3] == prefix and risk_key[-2] == reserve_class:
                    candidates.append(float(pyo.value(risk)))
        return max(candidates)

    @staticmethod
    def _reserve_total_expression(built: BuiltModel, key: Key) -> Any:
        case = built.case_data
        if not isinstance(case, ReserveCase) or case.reserve is None:
            raise TypeError("reserve surplus canonicalization requires ReserveCase")
        ca, dt, island, reserve_class = key
        offer_island = {
            (o_ca, o_dt, offer): o_island
            for o_ca, o_dt, offer, o_island in case.reserve.offer_island
        }
        reserve = built.artifacts["reserve"]
        return (
            sum(
                variable
                for reserve_key, variable in reserve.items()
                if reserve_key[:2] == (ca, dt)
                and reserve_key[3] == reserve_class
                and offer_island.get(reserve_key[:3]) == island
            )
            - built.artifacts["island_reserve"][key]
        )

    def _reserve_loss_targets(self, built: BuiltModel) -> dict[Key, float]:
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

    def _round_power_targets(
        self, built: BuiltModel
    ) -> dict[CanonicalTarget, float]:
        case = built.case_data
        if not isinstance(case, ReserveCase) or case.reserve is None:
            raise TypeError("reserve kink canonicalization requires ReserveCase")
        data = case.reserve
        sent = built.artifacts["hvdc_sent"]
        zones = built.artifacts["in_zone_binary"]
        candidates: dict[CanonicalTarget, float] = {}
        for island_key in sent:
            ca, dt, _island = island_key
            current = float(pyo.value(sent[island_key]))
            active_boundaries = {
                float(data.round_power_zone_exit[ca, dt, reserve_class])
                for reserve_class in RESERVE_CLASSES
                if data.reserve_round_power.get((ca, dt, reserve_class), 0.0)
                and float(
                    pyo.value(zones[*island_key, reserve_class, "RZ"])
                )
                >= 0.5
            }
            if len(active_boundaries) != 1:
                continue
            target = next(iter(active_boundaries))
            distance = current - target
            if (
                distance > self.equality_tolerance
                and distance <= self.maximum_round_power_distance_mw
            ):
                candidates[("hvdc_sent", island_key)] = target
        return candidates

    def _allowed_objective_loss(
        self, candidates: Mapping[CanonicalTarget, float]
    ) -> float:
        budgets = [
            self.surplus_objective_loss_budget
            if artifact_name == _RESERVE_TOTAL_TARGET
            else self.objective_loss_budget
            for artifact_name, _key in candidates
        ]
        if any(artifact_name == "hvdc_sent" for artifact_name, _key in candidates):
            budgets.append(self.round_power_objective_loss_budget)
        return max(budgets, default=self.objective_loss_budget)

    @staticmethod
    def _objective_loss(sense: Any, baseline: float, candidate: float) -> float:
        signed = baseline - candidate if sense is pyo.maximize else candidate - baseline
        return max(0.0, signed)

    @staticmethod
    def _named(values: Mapping[CanonicalTarget, float]) -> dict[str, float]:
        return {
            (
                "|".join(key)
                if artifact_name == "hvdc_reserve_sent"
                else "|".join((artifact_name, *key))
            ): value
            for (artifact_name, key), value in values.items()
        }


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
        intervals = ReservePriceIntervalAnalyzer().analyze(
            pricing,
            solve_result,
            reserve,
        )
        return ReservePrices(energy, reserve, reserve, intervals)


class ReservePriceIntervalAnalyzer:
    """Certify alternate reserve duals at exact and tolerance-level kinks.

    When both island reserve and all contributing offers are zero, the
    definition row can have a dual interval.  The loaded dual is one valid
    endpoint.  A small tightening of that row exposes the opposite one-sided
    marginal value.  A positive reserve quantity can likewise sit at the cheap
    tranche endpoint; a small relaxation exposes its other one-sided marginal.

    Historical CPLEX also accepts reserve-loss breakpoint states within its
    relative optimality tolerance.  A nearby breakpoint is admitted as an
    alternate price state only when an independent LP solve verifies both a
    1e-6 relative and a 0.1 NZD absolute objective bound.
    """

    perturbation_mw = 1e-4
    zero_tolerance = 1e-9
    endpoint_tolerance = 1e-5
    low_price_analysis_limit = 2e-2
    breakpoint_minimum_weight = 0.95
    relative_objective_budget = 1e-6
    absolute_objective_budget = 0.1

    def analyze(
        self,
        pricing: BuiltModel,
        outcome: HvdcSolveOutcome,
        reserve_prices: Mapping[Key, float],
    ) -> Mapping[Key, tuple[float, float]]:
        case = pricing.case_data
        if not isinstance(case, ReserveCase) or case.reserve is None:
            raise TypeError("reserve price interval analysis requires ReserveCase")
        data = case.reserve
        island_reserve = pricing.artifacts["island_reserve"]
        reserve = pricing.artifacts["reserve"]
        definitions = pricing.artifacts["island_reserve_definition"]
        offer_island = {
            tuple(item[:3]): item[3] for item in data.offer_island
        }
        intervals: dict[Key, tuple[float, float]] = {}
        for key, raw_price in reserve_prices.items():
            total_offer = sum(
                float(pyo.value(variable))
                for index, variable in reserve.items()
                if tuple(index[:2]) == key[:2]
                and index[3] == key[3]
                and offer_island.get(tuple(index[:3])) == key[2]
            )
            endpoint = self._cheapest_available_tranche(data, offer_island, key)
            if endpoint is None:
                continue
            zero_quantity = (
                abs(float(pyo.value(island_reserve[key]))) <= self.zero_tolerance
                and abs(total_offer) <= self.zero_tolerance
            )
            if zero_quantity and endpoint > raw_price + self.zero_tolerance:
                slope = self._perturbed_slope(
                    pricing, outcome, definitions[key], -self.perturbation_mw
                )
                if slope is not None and math.isclose(
                    slope,
                    endpoint,
                    rel_tol=0.0,
                    abs_tol=self.endpoint_tolerance,
                ):
                    intervals[key] = (
                        min(raw_price, endpoint),
                        max(raw_price, endpoint),
                    )
            elif raw_price <= self.low_price_analysis_limit or math.isclose(
                raw_price, endpoint, rel_tol=0.0, abs_tol=self.endpoint_tolerance
            ):
                slope = self._perturbed_slope(
                    pricing, outcome, definitions[key], self.perturbation_mw
                )
                if (
                    slope is not None
                    and abs(slope - raw_price) > self.endpoint_tolerance
                ):
                    intervals[key] = (
                        min(raw_price, slope),
                        max(raw_price, slope),
                    )
        self._nearby_breakpoint_intervals(
            pricing, outcome, reserve_prices, intervals
        )
        return MappingProxyType(intervals)

    def _cheapest_available_tranche(
        self,
        data: Any,
        offer_island: Mapping[Key, str],
        key: Key,
    ) -> float | None:
        candidates = [
            float(price)
            for block, price in data.reserve_block_price.items()
            if tuple(block[:2]) == key[:2]
            and block[4] == key[3]
            and offer_island.get(tuple(block[:3])) == key[2]
            and data.reserve_block_limit.get(tuple(block), 0.0)
            >= self.perturbation_mw
        ]
        return min(candidates) if candidates else None

    def _perturbed_slope(
        self,
        pricing: BuiltModel,
        outcome: HvdcSolveOutcome,
        source_constraint: Any,
        delta: float,
    ) -> float | None:
        model = self._clone_for_sensitivity(pricing)
        constraint = model.find_component(source_constraint.name)
        if constraint is None or constraint.upper is None:
            return None
        upper = float(pyo.value(constraint.upper))
        constraint.set_value(
            (
                constraint.lower,
                constraint.body,
                upper + delta,
            )
        )
        model.dual.clear()
        try:
            result = HighsBackend().solve(
                model,
                SolverConfiguration(
                    {
                        "solver": "simplex",
                        "primal_feasibility_tolerance": 1e-9,
                        "dual_feasibility_tolerance": 1e-9,
                        "primal_residual_tolerance": 1e-9,
                        "dual_residual_tolerance": 1e-9,
                        "random_seed": 0,
                        "threads": 1,
                    }
                ),
            )
        except SolverExecutionError:
            return None
        if not result.solution_loaded:
            return None
        objective = next(model.component_data_objects(pyo.Objective, active=True))
        candidate = float(pyo.value(objective))
        baseline = outcome.pricing_snapshot.objective
        if delta < 0.0:
            change = (
                baseline - candidate
                if objective.sense is pyo.maximize
                else candidate - baseline
            )
        else:
            change = (
                candidate - baseline
                if objective.sense is pyo.maximize
                else baseline - candidate
            )
        return change / abs(delta)

    @staticmethod
    def _clone_for_sensitivity(pricing: BuiltModel) -> Any:
        model = pricing.model.clone()
        if model.solutions is None:
            model.solutions = type(pricing.model.solutions)(model)
        return model

    def _nearby_breakpoint_intervals(
        self,
        pricing: BuiltModel,
        outcome: HvdcSolveOutcome,
        reserve_prices: Mapping[Key, float],
        intervals: dict[Key, tuple[float, float]],
    ) -> None:
        canonicalizer = ReserveKinkCanonicalizer(
            minimum_dominant_weight=self.breakpoint_minimum_weight
        )
        targets = canonicalizer._reserve_loss_targets(pricing)
        for target_key, target in targets.items():
            model = self._clone_for_sensitivity(pricing)
            source = pricing.artifacts["hvdc_reserve_sent"][target_key]
            variable = model.find_component(source.name)
            if variable is None:
                continue
            overlay = pyo.Constraint(expr=variable == target)
            model.add_component("ReservePriceIntervalBreakpoint", overlay)
            model.dual.clear()
            try:
                result = HighsBackend().solve(
                    model,
                    SolverConfiguration(
                        {
                            "solver": "simplex",
                            "primal_feasibility_tolerance": 1e-9,
                            "dual_feasibility_tolerance": 1e-9,
                            "primal_residual_tolerance": 1e-9,
                            "dual_residual_tolerance": 1e-9,
                            "random_seed": 0,
                            "threads": 1,
                        }
                    ),
                )
            except SolverExecutionError:
                continue
            if not result.solution_loaded:
                continue
            objective = next(model.component_data_objects(pyo.Objective, active=True))
            candidate = float(pyo.value(objective))
            loss = ReserveKinkCanonicalizer._objective_loss(
                objective.sense,
                outcome.pricing_snapshot.objective,
                candidate,
            )
            allowed = min(
                self.absolute_objective_budget,
                self.relative_objective_budget
                * abs(outcome.pricing_snapshot.objective),
            )
            if loss > allowed:
                continue
            definitions = pricing.artifacts["island_reserve_definition"]
            for key, raw_price in reserve_prices.items():
                constraint = model.find_component(definitions[key].name)
                if constraint is None or constraint not in model.dual:
                    continue
                alternate = float(model.dual[constraint])
                if abs(alternate - raw_price) <= self.endpoint_tolerance:
                    continue
                previous = intervals.get(key, (raw_price, raw_price))
                intervals[key] = (
                    min(previous[0], raw_price, alternate),
                    max(previous[1], raw_price, alternate),
                )


@dataclass(frozen=True, slots=True)
class ReservePrices:
    energy: NetworkPrices
    reserve: Mapping[Key, float]
    raw_reserve_duals: Mapping[Key, float]
    reserve_price_intervals: Mapping[Key, tuple[float, float]] = field(
        default_factory=dict
    )
    unit: str = "NZD/MWh"
    convention: str = "objective sensitivity to +1 MW available island reserve"

    def __post_init__(self) -> None:
        object.__setattr__(self, "reserve", MappingProxyType(dict(self.reserve)))
        object.__setattr__(
            self,
            "raw_reserve_duals",
            MappingProxyType(dict(self.raw_reserve_duals)),
        )
        object.__setattr__(
            self,
            "reserve_price_intervals",
            MappingProxyType(dict(self.reserve_price_intervals)),
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
