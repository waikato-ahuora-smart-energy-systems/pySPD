"""Gate 6 HVDC formulation and SCIP-MIP to fixed-HiGHS pricing state machine."""

from __future__ import annotations

from collections.abc import Mapping
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
from pyspd.hvdc.data import HVDC_FORMULATION_ID, HvdcCase
from pyspd.network.components import NetworkDomainsComponent
from pyspd.network.formulation import NetworkPrices, NetworkPricingEngine
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor
from pyspd.solver import (
    HighsBackend,
    MipSolveResult,
    NativeScipBackend,
    SolverConfiguration,
    SolveResult,
)

type Key = tuple[str, ...]

_SUPPORTED = frozenset({HVDC_FORMULATION_ID})
_SOS_STATE_CANONICALIZATION_TOLERANCE = 1e-5


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

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixed_discrete", MappingProxyType(dict(self.fixed_discrete))
        )
        object.__setattr__(
            self, "fixed_sos_members", MappingProxyType(dict(self.fixed_sos_members))
        )


class HvdcSolvePolicy(SolvePolicy):
    """Solve, detect, enforce, then price through an independent fixed RMIP."""

    supported_formulations = _SUPPORTED

    def solve(self, built_model: BuiltModel) -> HvdcSolveOutcome:
        case = built_model.case_data
        if not isinstance(case, HvdcCase) or case.hvdc is None:
            raise TypeError("HVDC solve policy requires HvdcCase")
        primary = built_model
        discrete = _active_discrete(primary.model)
        if discrete:
            initial: SolveResult | MipSolveResult = self._solve_scip(primary)
        else:
            initial = self._solve_highs(primary)
        issues = detect_nonphysical_hvdc(primary)
        primary_mip: MipSolveResult | None = (
            initial if isinstance(initial, MipSolveResult) else None
        )
        if issues and not (case.hvdc.enforce_sos2 and case.hvdc.enforce_flow_direction):
            enforced_case = replace(case, hvdc=case.hvdc.with_mip_enforcement())
            primary = ModelAssembler().assemble(self._formulation(), enforced_case)
            primary_mip = self._solve_scip(primary)
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
        pricing = ModelAssembler().assemble(self._formulation(), primary.case_data)
        _fix_and_relax_discrete(pricing.model, fixed)
        _fix_continuous_state(pricing.model, fixed_sos_members)
        _deactivate_sos(pricing.model)
        _assert_continuous_pricing_model(pricing.model)
        pricing_result = self._solve_highs(pricing)
        return HvdcSolveOutcome(
            primary,
            pricing,
            initial,
            primary_mip,
            pricing_result,
            issues,
            fixed,
            fixed_sos_members,
            _snapshot(primary),
            _snapshot(pricing),
        )

    def _formulation(self) -> Formulation:
        return hvdc_formulation()

    @staticmethod
    def _solve_scip(built: BuiltModel) -> MipSolveResult:
        return NativeScipBackend().solve_mip(
            built.model,
            SolverConfiguration(
                {
                    "time_limit_seconds": 300.0,
                    "relative_gap": 0.0,
                    "threads": 1,
                    "numerics/feastol": 1e-6,
                }
            ),
        )

    @staticmethod
    def _solve_highs(built: BuiltModel) -> SolveResult:
        return HighsBackend().solve(
            built.model,
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


def _solvefinal_sos_member_values(built: BuiltModel) -> dict[str, float]:
    """Capture members GAMS treats as discrete state during ``solveFinal``."""

    names = ("lambda_hvdc_energy", "lambda_hvdc_reserve")
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
    by_name = {
        variable.name: variable
        for variable in model.component_data_objects(pyo.Var, active=True)
    }
    missing = set(fixed) - set(by_name)
    if missing:
        raise ValueError("pricing model does not contain every SOS member")
    for name, value in fixed.items():
        by_name[name].fix(value)


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
    objective = next(built.model.component_data_objects(pyo.Objective, active=True))
    return SolutionSnapshot(
        built.formulation.formulation_id,
        float(pyo.value(objective)),
        {
            variable.name: _value(variable)
            for variable in built.model.component_data_objects(pyo.Var, active=True)
        },
        built.structural_signature,
    )


def _component_values(component: Any) -> dict[Key, float]:
    return {tuple(index): _value(component[index]) for index in component}


def _value(value: Any) -> float:
    evaluated = pyo.value(value, exception=False)
    return 0.0 if evaluated is None else float(evaluated)
