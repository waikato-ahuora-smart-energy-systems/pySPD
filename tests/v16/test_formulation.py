from __future__ import annotations

from datetime import date

from pyomo.repn.standard_repn import generate_standard_repn

from pyspd.application import PyspdApplication
from pyspd.architecture import ModelAssembler
from pyspd.reporting import Spd16DailyReportRenderer, Spd16DailyResultSchema
from pyspd.reserve import reserve_formulation
from pyspd.v16 import SPD16_FORMULATION_ID, IndependentSpd16Validator
from pyspd.v16.components import (
    Spd16BatteryModeComponent,
    Spd16ReserveEconomicsComponent,
    Spd16ReserveRequirementComponent,
    Spd16ReserveRiskComponent,
    Spd16TieBreakComponent,
)
from pyspd.v16.data import SPD16_RISK_CLASSES, Spd16Case
from pyspd.v16.formulation import (
    Spd16PricingEngine,
    Spd16ReportRenderer,
    Spd16ResultSchema,
    Spd16SolvePolicy,
    spd16_formulation,
)
from tests.reserve.conftest import make_reserve_case


def _generator_risk_effective_share_coefficients(built) -> tuple[float, ...]:
    generator_risk = built.artifacts["generator_island_risk"]
    effective_share = built.artifacts["reserve_share_effective"]
    coefficients: list[float] = []
    for row in built.model.ReserveRisk.Constraints.values():
        repn = generate_standard_repn(row.body, compute_values=True)
        if not any(
            variable.parent_component() is generator_risk
            for variable in repn.linear_vars
        ):
            continue
        coefficients.extend(
            float(coefficient)
            for variable, coefficient in zip(
                repn.linear_vars, repn.linear_coefs, strict=True
            )
            if variable.parent_component() is effective_share
        )
    return tuple(coefficients)


def test_v16_is_a_separately_composed_class_based_formulation() -> None:
    v5 = reserve_formulation()
    v16 = spd16_formulation()

    assert v16.formulation_id == SPD16_FORMULATION_ID
    assert Spd16TieBreakComponent in v16.components
    assert Spd16BatteryModeComponent in v16.components
    assert Spd16ReserveRiskComponent in v16.components
    assert Spd16ReserveRequirementComponent in v16.components
    assert Spd16ReserveEconomicsComponent in v16.components
    assert v16.solve_policy is Spd16SolvePolicy
    assert v16.pricing_engine is Spd16PricingEngine
    assert v16.result_schema is Spd16ResultSchema
    assert v16.report_renderer is Spd16ReportRenderer
    assert v5.formulation_id != v16.formulation_id
    assert Spd16TieBreakComponent not in v5.components


def test_v16_is_explicitly_selectable_in_application_and_reporting() -> None:
    application = PyspdApplication()
    profile = application.report_registry.resolve(SPD16_FORMULATION_ID)

    assert SPD16_FORMULATION_ID in application.formulation_ids
    assert profile.result_schema is Spd16DailyResultSchema
    assert profile.report_renderer is Spd16DailyReportRenderer


def test_v16_zero_reserve_price_uses_sum_of_requirement_duals() -> None:
    assert (
        Spd16PricingEngine.select_reserve_price(
            island_reserve_mw=0.0,
            definition_dual=99.0,
            requirement_duals=(2.0, 3.5, -0.5),
        )
        == 5.0
    )
    assert (
        Spd16PricingEngine.select_reserve_price(
            island_reserve_mw=1.0,
            definition_dual=7.0,
            requirement_duals=(2.0, 3.5),
        )
        == 7.0
    )


def test_v16_assembles_and_runs_scip_then_fixed_highs_rmip() -> None:
    case = Spd16Case.from_reserve_case(
        make_reserve_case(), source_date=date(2026, 6, 23)
    )
    built = ModelAssembler().assemble(spd16_formulation(), case)

    assert set(built.model.ReserveDomains.RiskClass) == set(SPD16_RISK_CLASSES)
    assert built.artifacts.owners["island_risk"] == "reserve_risk"
    assert built.artifacts.owners["reserve_requirement"] == "reserve_requirement"
    outcome = Spd16SolvePolicy().solve(built)
    assert outcome.primary_mip is not None
    assert outcome.primary_mip.solve.backend == "native-scip"
    assert outcome.primary_mip.solve.status.value == "optimal"
    assert outcome.pricing_lp.backend == "highs"
    assert outcome.pricing_lp.status.value == "optimal"
    prices = Spd16PricingEngine().price(built, outcome)
    assert prices.reserve
    validation = IndependentSpd16Validator().validate(outcome, prices.reserve)
    assert validation.passed, validation.residuals


def test_v16_generator_risk_is_gross_of_effective_shared_reserve() -> None:
    base = make_reserve_case()
    v5 = ModelAssembler().assemble(reserve_formulation(), base)
    v16 = ModelAssembler().assemble(
        spd16_formulation(),
        Spd16Case.from_reserve_case(base, source_date=date(2026, 6, 23)),
    )

    assert _generator_risk_effective_share_coefficients(v5)
    assert _generator_risk_effective_share_coefficients(v16) == ()
