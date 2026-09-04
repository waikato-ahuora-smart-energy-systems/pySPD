"""Gate 6 HVDC formulation and SCIP-MIP to fixed-HiGHS pricing state machine."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from itertools import pairwise
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
    HVDCEconomicsComponent,
    HVDCSecurityComponent,
    HVDCTransmissionComponent,
)
from pyspd.hvdc.data import HVDC_FORMULATION_ID, HvdcCase, SosRepresentation
from pyspd.network.components import NetworkDomainsComponent
from pyspd.network.formulation import NetworkPrices, NetworkPricingEngine
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor
from pyspd.solver import (
    CbcBackend,
    ClpBackend,
    HighsBackend,
    MipSolveResult,
    NativeScipBackend,
    SolverBackend,
    SolverConfiguration,
    SolveResult,
    SolverExecutionError,
)

type Key = tuple[str, ...]

_SUPPORTED = frozenset({HVDC_FORMULATION_ID})
# Match the governed GAMS ``solveFinal`` overlay: a solved SOS member is
# inactive only when its magnitude is at or below 1e-7.  A wider threshold can
# erase a legitimate adjacent member and over-constrain the fixed RMIP.
_SOS_STATE_CANONICALIZATION_TOLERANCE = 1e-7
_SCIP_STRICT_PRIMAL_FEASIBILITY_TOLERANCE = 1e-7
_SCIP_STABLE_PRIMAL_FEASIBILITY_TOLERANCE = 1e-6
_FIXED_RMIP_OBJECTIVE_TOLERANCE = 1e-6


class HvdcPreprocessor(PreprocessorStep):
    supported_formulations = _SUPPORTED

    def transform(self, case_data: Any) -> HvdcCase:
        if isinstance(case_data, HvdcCase):
            return case_data
        if not isinstance(case_data, CaseData):
            raise TypeError("HVDC preprocessing requires CaseData")
        result = Vspd506Preprocessor(
            PreprocessingSettings(apply_rtd_load_reconstruction=True)
        ).transform(case_data)
        return HvdcCase.from_sources(result, case_data)


@dataclass(frozen=True, slots=True)
class SolutionSnapshot:
    formulation_id: str
    objective: float
    variables: Mapping[str, float]
    structural_signature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", MappingProxyType(dict(self.variables)))

    @classmethod
    def capture(cls, built: BuiltModel) -> SolutionSnapshot:
        objective = next(
            built.model.component_data_objects(pyo.Objective, active=True)
        )
        return cls(
            built.formulation.formulation_id,
            float(pyo.value(objective)),
            {
                variable.name: _value(variable)
                for variable in built.model.component_data_objects(
                    pyo.Var, active=True
                )
            },
            built.structural_signature,
        )


@dataclass(frozen=True, slots=True)
class PricingCanonicalizationAudit:
    """Auditable secondary pricing solve within a declared objective budget."""

    policy: str
    candidate_targets: Mapping[str, float]
    accepted_targets: Mapping[str, float]
    baseline_objective: float
    canonical_objective: float
    objective_loss: float
    allowed_objective_loss: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_targets", MappingProxyType(dict(self.candidate_targets))
        )
        object.__setattr__(
            self, "accepted_targets", MappingProxyType(dict(self.accepted_targets))
        )


@dataclass(frozen=True, slots=True)
class SosSupportPolishingAudit:
    """Fail-closed evidence for objective-improving native SOS support repair."""

    policy: str
    attempted: bool
    accepted: bool
    reason: str
    baseline_objective: float
    discovery_objective: float
    polished_objective: float
    objective_improvement: float
    inactive_member_count: int


type WarmStartKey = tuple[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class WarmStartSnapshot:
    """Period-neutral primal values that can seed a freshly built model."""

    values: Mapping[WarmStartKey, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    @classmethod
    def capture(
        cls,
        model: pyo.ConcreteModel,
        *,
        discrete_only: bool = False,
    ) -> WarmStartSnapshot:
        values: dict[WarmStartKey, float] = {}
        for variable in model.component_data_objects(pyo.Var, active=True):
            if discrete_only and not (variable.is_binary() or variable.is_integer()):
                continue
            value = pyo.value(variable, exception=False)
            if value is None or not math.isfinite(float(value)):
                continue
            key = _warm_start_key(variable)
            if key in values:
                raise ValueError(f"duplicate period-neutral warm-start key: {key!r}")
            values[key] = float(value)
        return cls(values)

    def apply(
        self,
        model: pyo.ConcreteModel,
        *,
        discrete_only: bool = False,
    ) -> int:
        applied = 0
        for variable in model.component_data_objects(pyo.Var, active=True):
            if variable.fixed:
                continue
            if discrete_only and not (variable.is_binary() or variable.is_integer()):
                continue
            value = self.values.get(_warm_start_key(variable))
            if value is None or not _warm_start_value_is_valid(variable, value):
                continue
            if variable.is_binary() or variable.is_integer():
                value = float(round(value))
            variable.set_value(value, skip_validation=True)
            applied += 1
        return applied


@dataclass(frozen=True, slots=True)
class WarmStartAudit:
    enabled: bool
    prior_value_count: int
    primary_discrete_count: int
    pricing_value_count: int


@dataclass(frozen=True, slots=True)
class HvdcSolveOutcome:
    primary_model: BuiltModel
    pricing_model: BuiltModel
    initial_solve: SolveResult | MipSolveResult
    primary_mip: MipSolveResult | None
    pricing_lp: SolveResult
    detected_issues: tuple[str, ...]
    fixed_discrete: Mapping[str, float]
    fixed_sos_members: Mapping[str, float]
    primary_snapshot: SolutionSnapshot
    pricing_snapshot: SolutionSnapshot
    next_warm_start: WarmStartSnapshot
    warm_start: WarmStartAudit
    solver_profile: str
    sos_support_polishing: SosSupportPolishingAudit | None = None
    pricing_canonicalization: PricingCanonicalizationAudit | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixed_discrete", MappingProxyType(dict(self.fixed_discrete))
        )
        object.__setattr__(
            self, "fixed_sos_members", MappingProxyType(dict(self.fixed_sos_members))
        )


class SosSupportPolisher:
    """Compare native SOS2 support with an explicit interval-binary support.

    Native SCIP SOS2 solves can terminate with a numerically acceptable but
    economically inferior adjacent support.  A second SCIP solve fixes every
    ordinary discrete decision and lets only the explicit SOS2 interval
    binaries choose an alternative support.  That support is independently
    fixed and repriced.  It replaces the native support only when the final
    RMIP objective is strictly better; ties retain the qualified native path.
    """

    policy = "objective-improving-adjacent-sos-support-v1"

    def __init__(
        self,
        *,
        support_tolerance: float = _SOS_STATE_CANONICALIZATION_TOLERANCE,
        minimum_objective_improvement: float = 1e-8,
    ) -> None:
        if support_tolerance < 0.0 or minimum_objective_improvement < 0.0:
            raise ValueError("SOS support-polishing tolerances cannot be negative")
        self.support_tolerance = float(support_tolerance)
        self.minimum_objective_improvement = float(minimum_objective_improvement)

    def polish(
        self,
        primary: BuiltModel,
        formulation: Formulation,
        fixed_discrete: Mapping[str, float],
        baseline_model: BuiltModel,
        baseline_result: SolveResult,
        baseline_snapshot: SolutionSnapshot,
        solve_mip: Callable[[BuiltModel], MipSolveResult],
        solve_pricing: Callable[[BuiltModel], SolveResult],
    ) -> tuple[
        BuiltModel,
        SolveResult,
        SolutionSnapshot,
        SosSupportPolishingAudit,
    ]:
        case = primary.case_data
        if not isinstance(case, HvdcCase) or case.hvdc is None:
            raise TypeError("SOS support polishing requires an HVDC case")
        portable_case = replace(
            case,
            hvdc=replace(
                case.hvdc,
                sos_representation=SosRepresentation.PORTABLE,
            ),
        )
        discovery = ModelAssembler().assemble(formulation, portable_case)
        _fix_existing_discrete(discovery.model, fixed_discrete)
        try:
            solve_mip(discovery)
        except SolverExecutionError:
            return self._rejected(
                baseline_model,
                baseline_result,
                baseline_snapshot,
                baseline_snapshot.objective,
                0.0,
                0,
                "support-oracle-solve-failed",
            )
        candidate_fixed = _discrete_values(discovery.model)
        candidate_support = _solvefinal_sos_member_values(discovery)
        inactive_count = sum(value == 0.0 for value in candidate_support.values())
        if not self._support_is_adjacent(discovery):
            return self._rejected(
                baseline_model,
                baseline_result,
                baseline_snapshot,
                baseline_snapshot.objective,
                0.0,
                inactive_count,
                "non-adjacent-portable-support",
            )

        candidate = ModelAssembler().assemble(formulation, portable_case)
        _fix_and_relax_discrete(candidate.model, candidate_fixed)
        _fix_continuous_state(candidate.model, candidate_support)
        _deactivate_sos(candidate.model)
        _assert_continuous_pricing_model(candidate.model)
        candidate_result = solve_pricing(candidate)
        candidate_snapshot = _snapshot(candidate)
        objective = next(
            candidate.model.component_data_objects(pyo.Objective, active=True)
        )
        improvement = self._objective_improvement(
            objective.sense,
            baseline_snapshot.objective,
            candidate_snapshot.objective,
        )
        if improvement <= self.minimum_objective_improvement:
            return self._rejected(
                baseline_model,
                baseline_result,
                baseline_snapshot,
                candidate_snapshot.objective,
                improvement,
                inactive_count,
                "no-material-objective-improvement",
            )
        audit = SosSupportPolishingAudit(
            self.policy,
            True,
            True,
            "objective-improving-adjacent-support",
            baseline_snapshot.objective,
            candidate_snapshot.objective,
            candidate_snapshot.objective,
            improvement,
            inactive_count,
        )
        return candidate, candidate_result, candidate_snapshot, audit

    def _rejected(
        self,
        baseline_model: BuiltModel,
        baseline_result: SolveResult,
        baseline_snapshot: SolutionSnapshot,
        discovery_objective: float,
        improvement: float,
        inactive_count: int,
        reason: str,
    ) -> tuple[
        BuiltModel,
        SolveResult,
        SolutionSnapshot,
        SosSupportPolishingAudit,
    ]:
        audit = SosSupportPolishingAudit(
            self.policy,
            True,
            False,
            reason,
            baseline_snapshot.objective,
            discovery_objective,
            baseline_snapshot.objective,
            max(0.0, improvement),
            inactive_count,
        )
        return baseline_model, baseline_result, baseline_snapshot, audit

    def _support_is_adjacent(self, built: BuiltModel) -> bool:
        for artifact_name in (
            "hvdc_lambda",
            "lambda_hvdc_energy",
            "lambda_hvdc_reserve",
        ):
            if artifact_name not in built.artifacts.values:
                continue
            component = built.artifacts[artifact_name]
            grouped: dict[tuple[str, ...], list[int]] = {}
            breakpoints: dict[tuple[str, ...], list[str]] = {}
            for raw_key in component:
                key = tuple(str(token) for token in raw_key)
                group = key[:-1]
                breakpoints.setdefault(group, []).append(key[-1])
            for group, labels in breakpoints.items():
                grouped[group] = [
                    position
                    for position, label in enumerate(labels)
                    if _value(component[*group, label]) > self.support_tolerance
                ]
            if any(
                len(active) > 2
                or (len(active) == 2 and active[1] - active[0] != 1)
                for active in grouped.values()
            ):
                return False
        return True

    @staticmethod
    def _objective_improvement(sense: Any, baseline: float, candidate: float) -> float:
        return candidate - baseline if sense is pyo.maximize else baseline - candidate


class HvdcSolvePolicy(SolvePolicy):
    """Solve, detect, enforce, then price through an independent fixed RMIP."""

    supported_formulations = _SUPPORTED

    def __init__(
        self,
        *,
        warm_start_primary: bool = False,
        warm_start_pricing: bool = False,
        previous_period_start: WarmStartSnapshot | None = None,
        primary_backend: SolverBackend | None = None,
        pricing_backend: SolverBackend | None = None,
    ) -> None:
        self.warm_start_primary = bool(warm_start_primary)
        self.warm_start_pricing = bool(warm_start_pricing)
        self.previous_period_start = previous_period_start
        self.primary_backend = primary_backend
        self.pricing_backend = pricing_backend

    def solve(self, built_model: BuiltModel) -> HvdcSolveOutcome:
        case = built_model.case_data
        if not isinstance(case, HvdcCase) or case.hvdc is None:
            raise TypeError("HVDC solve policy requires HvdcCase")
        primary = built_model
        prior = self.previous_period_start if self.warm_start_primary else None
        prior_value_count = len(prior.values) if prior is not None else 0
        primary_warm_count = (
            prior.apply(primary.model, discrete_only=True) if prior is not None else 0
        )
        discrete = _active_discrete(primary.model)
        if discrete:
            initial: SolveResult | MipSolveResult = self._solve_primary_mip(
                primary,
                warm_start=primary_warm_count > 0,
            )
        else:
            primary_warm_count = prior.apply(primary.model) if prior is not None else 0
            initial = self._solve_highs(
                primary,
                warm_start=primary_warm_count > 0,
            )
        issues = detect_nonphysical_hvdc(primary)
        primary_mip: MipSolveResult | None = (
            initial if isinstance(initial, MipSolveResult) else None
        )
        if issues and not (case.hvdc.enforce_sos2 and case.hvdc.enforce_flow_direction):
            enforced_case = replace(case, hvdc=case.hvdc.with_mip_enforcement())
            primary = ModelAssembler().assemble(self._formulation(), enforced_case)
            primary_warm_count = (
                prior.apply(primary.model, discrete_only=True)
                if prior is not None
                else 0
            )
            primary_mip = self._solve_primary_mip(
                primary,
                warm_start=primary_warm_count > 0,
            )
            remaining = detect_nonphysical_hvdc(primary)
            if remaining:
                raise ValueError(
                    "HVDC MIP enforcement did not eliminate: " + ", ".join(remaining)
                )
        final_solve = primary_mip.solve if primary_mip is not None else initial
        assert isinstance(final_solve, SolveResult)
        if not final_solve.solution_loaded:
            raise ValueError("primary solution was not loaded")
        fixed = _discrete_values(primary.model)
        fixed_sos_members = _solvefinal_sos_member_values(primary)
        _set_continuous_state(primary.model, fixed_sos_members)
        primary_snapshot = _snapshot(primary)
        pricing = ModelAssembler().assemble(self._formulation(), primary.case_data)
        pricing_warm_count = 0
        if self.warm_start_pricing and self.pricing_backend is None:
            pricing_warm_count = WarmStartSnapshot.capture(primary.model).apply(
                pricing.model
            )
        _fix_and_relax_discrete(pricing.model, fixed)
        _fix_continuous_state(pricing.model, fixed_sos_members)
        _deactivate_sos(pricing.model)
        _assert_continuous_pricing_model(pricing.model)
        pricing_result = self._solve_pricing(pricing, warm_start=pricing_warm_count > 0)
        pricing_snapshot = _snapshot(pricing)
        support_audit: SosSupportPolishingAudit | None = None
        primary_options = final_solve.options
        used_stable_scip_fallback = (
            float(primary_options.get("numerics/feastol", 0.0))
            > _SCIP_STRICT_PRIMAL_FEASIBILITY_TOLERANCE
        )
        native_sos = case.hvdc.sos_representation is SosRepresentation.NATIVE
        if self._support_polishing_required(
            native_sos=native_sos,
            used_stable_scip_fallback=used_stable_scip_fallback,
            primary_objective=primary_snapshot.objective,
            pricing_objective=pricing_snapshot.objective,
        ):
            pricing, pricing_result, pricing_snapshot, support_audit = (
                SosSupportPolisher().polish(
                    primary,
                    self._formulation(),
                    fixed,
                    pricing,
                    pricing_result,
                    pricing_snapshot,
                    self._solve_support_mip,
                    self._solve_pricing,
                )
            )
        elif native_sos:
            support_audit = SosSupportPolishingAudit(
                SosSupportPolisher.policy,
                False,
                False,
                "strict-native-scip-support",
                pricing_snapshot.objective,
                pricing_snapshot.objective,
                pricing_snapshot.objective,
                0.0,
                sum(value == 0.0 for value in fixed_sos_members.values()),
            )
        next_warm_start = (
            WarmStartSnapshot.capture(primary.model, discrete_only=True)
            if self.warm_start_primary
            else WarmStartSnapshot({})
        )
        return HvdcSolveOutcome(
            primary,
            pricing,
            initial,
            primary_mip,
            pricing_result,
            issues,
            fixed,
            fixed_sos_members,
            primary_snapshot,
            pricing_snapshot,
            next_warm_start,
            WarmStartAudit(
                self.warm_start_primary or self.warm_start_pricing,
                prior_value_count,
                primary_warm_count,
                pricing_warm_count,
            ),
            self.solver_profile,
            support_audit,
        )

    @staticmethod
    def _support_polishing_required(
        *,
        native_sos: bool,
        used_stable_scip_fallback: bool,
        primary_objective: float,
        pricing_objective: float,
    ) -> bool:
        return native_sos and (
            used_stable_scip_fallback
            or abs(primary_objective - pricing_objective)
            > _FIXED_RMIP_OBJECTIVE_TOLERANCE
        )

    @property
    def solver_profile(self) -> str:
        primary = self.primary_backend.name if self.primary_backend else "scip"
        backend = self.pricing_backend.name if self.pricing_backend else "highs"
        return f"{primary}-mip-fixed-{backend}-rmip"

    def _solve_primary_mip(
        self,
        built: BuiltModel,
        *,
        warm_start: bool = False,
    ) -> MipSolveResult:
        if self.primary_backend is None:
            return self._solve_scip(built, warm_start=warm_start)
        if isinstance(self.primary_backend, CbcBackend):
            return self.primary_backend.solve_mip(
                built.model,
                SolverConfiguration(
                    {
                        "time_limit_seconds": 300.0,
                        "relative_gap": 0.0,
                        "threads": 1,
                    }
                ),
                warm_start_discrete=warm_start,
            )
        solve_mip = getattr(self.primary_backend, "solve_mip", None)
        if solve_mip is None:
            raise TypeError("primary backend must implement solve_mip")
        return solve_mip(built.model, warm_start_discrete=warm_start)

    @staticmethod
    def _solve_support_mip(built: BuiltModel) -> MipSolveResult:
        """Select only explicit SOS intervals under a tighter numeric contract."""

        return NativeScipBackend().solve_mip(
            built.model,
            SolverConfiguration(
                {
                    "time_limit_seconds": 300.0,
                    "relative_gap": 0.0,
                    "threads": 1,
                    "numerics/feastol": 1e-9,
                    "limits/absgap": 0.0,
                    "lp/initalgorithm": "d",
                    "lp/resolvealgorithm": "d",
                    "misc/usesymmetry": 0,
                }
            ),
        )

    def _solve_pricing(
        self,
        built: BuiltModel,
        *,
        warm_start: bool = False,
    ) -> SolveResult:
        if self.pricing_backend is None:
            return self._solve_highs(built, warm_start=warm_start)
        if isinstance(self.pricing_backend, ClpBackend):
            return self.pricing_backend.solve(
                built.model,
                SolverConfiguration(
                    {
                        "primal_feasibility_tolerance": 1e-9,
                        "dual_feasibility_tolerance": 1e-9,
                        "log_level": 0,
                    }
                ),
            )
        return self.pricing_backend.solve(built.model)

    def _formulation(self) -> Formulation:
        return hvdc_formulation()

    @staticmethod
    def _solve_scip(
        built: BuiltModel,
        *,
        warm_start: bool = False,
    ) -> MipSolveResult:
        case = built.case_data
        native_sos = (
            isinstance(case, HvdcCase)
            and case.hvdc is not None
            and case.hvdc.sos_representation is SosRepresentation.NATIVE
        )
        options: dict[str, int | float | str] = {
            "time_limit_seconds": 300.0,
            "relative_gap": 0.0,
            "threads": 1,
            "numerics/feastol": (
                _SCIP_STRICT_PRIMAL_FEASIBILITY_TOLERANCE
                if native_sos
                else _SCIP_STABLE_PRIMAL_FEASIBILITY_TOLERANCE
            ),
            "lp/initalgorithm": "d",
            "lp/resolvealgorithm": "d",
            # Legacy daily inputs contain large inactive-period symmetries.
            # SCIP's symmetry cuts are unnecessary for vSPD's small active
            # binary surface and can make SoPlex numerically unstable.
            "misc/usesymmetry": 0,
        }
        try:
            return NativeScipBackend().solve_mip(
                built.model,
                SolverConfiguration(options),
                warm_start_discrete=warm_start,
            )
        except SolverExecutionError as error:
            if "LP solver" not in str(error):
                raise
            # Some legacy matrices make SoPlex reject the strict tolerance.
            # Retain the historically stable setting as an explicit fallback;
            # its SOS support is then independently challenged by the support
            # polisher before prices are accepted.
            stable = (
                options
                if not native_sos
                else options
                | {
                    "numerics/feastol": _SCIP_STABLE_PRIMAL_FEASIBILITY_TOLERANCE
                }
            )
            if not native_sos:
                return NativeScipBackend().solve_mip(
                    built.model,
                    SolverConfiguration(stable | {"presolving/maxrounds": 0}),
                    warm_start_discrete=warm_start,
                )
            try:
                return NativeScipBackend().solve_mip(
                    built.model,
                    SolverConfiguration(stable),
                    warm_start_discrete=warm_start,
                )
            except SolverExecutionError as error:
                if "LP solver" not in str(error):
                    raise
                return NativeScipBackend().solve_mip(
                    built.model,
                    SolverConfiguration(stable | {"presolving/maxrounds": 0}),
                    warm_start_discrete=warm_start,
                )

    @staticmethod
    def _solve_highs(
        built: BuiltModel,
        *,
        warm_start: bool = False,
    ) -> SolveResult:
        return HighsBackend().solve(
            built.model,
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
            warm_start=warm_start,
        )


class HvdcPricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED

    def price(
        self, built_model: BuiltModel, solve_result: HvdcSolveOutcome
    ) -> NetworkPrices:
        if not pricing_model_belongs_to_request(
            built_model, solve_result.primary_model
        ):
            raise ValueError("pricing outcome does not belong to the requested case")
        return NetworkPricingEngine().price(
            solve_result.pricing_model, solve_result.pricing_lp
        )


def pricing_model_belongs_to_request(
    requested_model: BuiltModel, primary_model: BuiltModel
) -> bool:
    """Accept the requested case or its exact automatic MIP-enforcement form."""

    if primary_model is requested_model:
        return True
    requested = requested_model.case_data
    primary = primary_model.case_data
    if primary == requested:
        return True
    if (
        not isinstance(requested, HvdcCase)
        or not isinstance(primary, HvdcCase)
        or requested.hvdc is None
    ):
        return False
    return primary == replace(
        requested,
        hvdc=requested.hvdc.with_mip_enforcement(),
    )


@dataclass(frozen=True, slots=True)
class HvdcResults:
    generation: Mapping[Key, float]
    purchases: Mapping[Key, float]
    ac_branch_flow: Mapping[Key, float]
    hvdc_flow: Mapping[Key, float]
    hvdc_loss: Mapping[Key, float]
    primary_objective: float
    pricing_objective: float
    fixed_discrete: Mapping[str, float]

    def __post_init__(self) -> None:
        for name in (
            "generation",
            "purchases",
            "ac_branch_flow",
            "hvdc_flow",
            "hvdc_loss",
            "fixed_discrete",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


class HvdcResultSchema(ResultSchema):
    supported_formulations = _SUPPORTED

    def collect(
        self, built_model: BuiltModel, solve_result: HvdcSolveOutcome
    ) -> HvdcResults:
        primary = solve_result.primary_model
        return HvdcResults(
            _component_values(primary.artifacts["generation"]),
            _component_values(primary.artifacts["purchase"]),
            _component_values(primary.artifacts["branch_flow"]),
            _component_values(primary.artifacts["hvdc_flow"]),
            _component_values(primary.artifacts["hvdc_loss"]),
            solve_result.primary_snapshot.objective,
            solve_result.pricing_snapshot.objective,
            solve_result.fixed_discrete,
        )


class HvdcReportRenderer(ReportRenderer):
    supported_formulations = _SUPPORTED

    def render(self, results: Any) -> Mapping[str, Any]:
        if not isinstance(results, HvdcResults):
            raise TypeError("renderer requires HvdcResults")
        return MappingProxyType(
            {
                "generation_mw": dict(results.generation),
                "purchase_mw": dict(results.purchases),
                "ac_branch_flow_mw": dict(results.ac_branch_flow),
                "hvdc_flow_mw": dict(results.hvdc_flow),
                "hvdc_loss_mw": dict(results.hvdc_loss),
                "primary_objective_nzd": results.primary_objective,
                "pricing_objective_nzd": results.pricing_objective,
                "fixed_discrete": dict(results.fixed_discrete),
            }
        )


def hvdc_formulation(*, preprocess: bool = False) -> Formulation:
    return Formulation(
        formulation_id=HVDC_FORMULATION_ID,
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
            HVDCSecurityComponent,
            HVDCEconomicsComponent,
        ),
        preprocessors=(HvdcPreprocessor,) if preprocess else (),
        solve_policy=HvdcSolvePolicy,
        pricing_engine=HvdcPricingEngine,
        result_schema=HvdcResultSchema,
        report_renderer=HvdcReportRenderer,
    )


def detect_nonphysical_hvdc(built_model: BuiltModel) -> tuple[str, ...]:
    case = built_model.case_data
    if not isinstance(case, HvdcCase) or case.hvdc is None:
        raise TypeError("HVDC detector requires HvdcCase")
    data = case.hvdc
    flow = built_model.artifacts["hvdc_flow"]
    lambdas = built_model.artifacts["hvdc_lambda"]
    issues: list[str] = []
    for period in case.periods:
        direction_flow = {
            direction: sum(
                _value(flow[link])
                for link in data.links
                if link[:2] == period and data.link_direction[link] == direction
            )
            for direction in ("forward", "backward")
        }
        if min(direction_flow.values()) > data.circulation_tolerance:
            issues.append(f"circulation:{period}")
    for link in data.links:
        active_orders = sorted(
            data.breakpoint_order[key]
            for key in data.breakpoints
            if key[:3] == link
            and _value(lambdas[key]) > data.nonphysical_loss_tolerance
        )
        if len(active_orders) > 1 and any(
            right - left > 1.0 for left, right in pairwise(active_orders)
        ):
            issues.append(f"nonadjacent-lambda:{link}")
    return tuple(issues)


def _active_discrete(model: pyo.ConcreteModel) -> tuple[Any, ...]:
    return tuple(
        variable
        for variable in model.component_data_objects(pyo.Var, active=True)
        if not variable.fixed and (variable.is_binary() or variable.is_integer())
    )


def _warm_start_key(variable: Any) -> WarmStartKey:
    index = variable.index()
    if index is None:
        tokens: tuple[Any, ...] = ()
    elif isinstance(index, tuple):
        tokens = index
    else:
        tokens = (index,)
    # Every operational case model contains one case/date pair. Removing it
    # creates a stable semantic identity for the canonical successor period.
    if len(tokens) >= 2:
        tokens = tokens[2:]
    return variable.parent_component().name, tuple(str(token) for token in tokens)


def _warm_start_value_is_valid(variable: Any, value: float) -> bool:
    if not math.isfinite(value):
        return False
    lower = pyo.value(variable.lb, exception=False)
    upper = pyo.value(variable.ub, exception=False)
    tolerance = 1e-7
    if lower is not None and value < float(lower) - tolerance:
        return False
    if upper is not None and value > float(upper) + tolerance:
        return False
    return not (
        (variable.is_binary() or variable.is_integer())
        and abs(value - round(value)) > tolerance
    )


def _discrete_values(model: pyo.ConcreteModel) -> dict[str, float]:
    return {
        variable.name: round(_value(variable))
        for variable in model.component_data_objects(pyo.Var, active=True)
        if variable.is_binary() or variable.is_integer()
    }


def _fix_and_relax_discrete(
    model: pyo.ConcreteModel, fixed: Mapping[str, float]
) -> None:
    by_name = {
        variable.name: variable
        for variable in model.component_data_objects(pyo.Var, active=True)
    }
    if set(by_name) < set(fixed):
        raise ValueError("pricing model does not contain every discrete decision")
    for name, value in fixed.items():
        variable = by_name[name]
        variable.fix(value)
        variable.domain = pyo.Reals
    # Variables fixed by formulation preprocessing (for example unavailable
    # NMIR zones) are not part of the incumbent fix map, but their discrete
    # domains must also be relaxed or HiGHS still treats the pricing model as a
    # MIP and cannot return RMIP duals.
    for variable in model.component_data_objects(pyo.Var, active=True):
        if variable.is_binary() or variable.is_integer():
            variable.domain = pyo.Reals


def _fix_existing_discrete(
    model: pyo.ConcreteModel, fixed: Mapping[str, float]
) -> None:
    """Fix a known discrete subset while retaining new interval binaries."""

    by_name = {
        variable.name: variable
        for variable in model.component_data_objects(pyo.Var, active=True)
    }
    missing = set(fixed) - set(by_name)
    if missing:
        raise ValueError("support-discovery model lacks an ordinary discrete decision")
    for name, value in fixed.items():
        by_name[name].fix(value)


def _solvefinal_sos_member_values(built: BuiltModel) -> dict[str, float]:
    """Capture members GAMS treats as discrete state during ``solveFinal``."""

    names = ("hvdc_lambda", "lambda_hvdc_energy", "lambda_hvdc_reserve")
    return {
        variable.name: _canonical_sos_value(_value(variable))
        for name in names
        if name in built.artifacts.values
        for variable in built.artifacts[name].values()
    }


def _canonical_sos_value(
    value: float, *, tolerance: float = _SOS_STATE_CANONICALIZATION_TOLERANCE
) -> float:
    """Remove solver-feasibility residue before fixing SOS state in the RMIP."""

    if abs(value) <= tolerance:
        return 0.0
    if abs(value - 1.0) <= tolerance:
        return 1.0
    return value


def _fix_continuous_state(model: pyo.ConcreteModel, fixed: Mapping[str, float]) -> None:
    """Preserve solved SOS support while leaving active weights continuous.

    The fixed-discrete pricing model must retain the primary solve's selected
    SOS interval, but fixing the nonzero interpolation weights over-constrains
    the RMIP and can make it infeasible.  Zero-valued members define the
    inactive support; the interval binaries fixed by ``_fix_and_relax_discrete``
    constrain the remaining weights.
    """

    by_name = {
        variable.name: variable
        for variable in model.component_data_objects(pyo.Var, active=True)
    }
    missing = set(fixed) - set(by_name)
    if missing:
        raise ValueError("pricing model does not contain every SOS member")
    for name, value in fixed.items():
        if value == 0.0:
            by_name[name].fix(0.0)


def _set_continuous_state(
    model: pyo.ConcreteModel, values: Mapping[str, float]
) -> None:
    """Write canonical solve-final values back to the primary evidence model."""

    by_name = {
        variable.name: variable
        for variable in model.component_data_objects(pyo.Var, active=True)
    }
    missing = set(values) - set(by_name)
    if missing:
        raise ValueError("primary model does not contain every SOS member")
    for name, value in values.items():
        by_name[name].set_value(value)


def _deactivate_sos(model: pyo.ConcreteModel) -> None:
    for component in model.component_objects(pyo.SOSConstraint, active=True):
        component.deactivate()


def _assert_continuous_pricing_model(model: pyo.ConcreteModel) -> None:
    remaining = _active_discrete(model)
    active_sos = tuple(model.component_data_objects(pyo.SOSConstraint, active=True))
    if remaining or active_sos:
        raise ValueError(
            f"pricing RMIP retains discrete={len(remaining)}, SOS={len(active_sos)}"
        )


def _snapshot(built: BuiltModel) -> SolutionSnapshot:
    return SolutionSnapshot.capture(built)


def _component_values(component: Any) -> dict[Key, float]:
    return {tuple(index): _value(component[index]) for index in component}


def _value(value: Any) -> float:
    evaluated = pyo.value(value, exception=False)
    return 0.0 if evaluated is None else float(evaluated)
