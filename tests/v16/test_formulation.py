from __future__ import annotations

from pyspd.application import PyspdApplication
from pyspd.reporting import Spd16DailyReportRenderer, Spd16DailyResultSchema
from pyspd.reserve import reserve_formulation
from pyspd.v16 import SPD16_FORMULATION_ID
from pyspd.v16.components import (
    Spd16BatteryModeComponent,
    Spd16ReserveEconomicsComponent,
    Spd16ReserveRequirementComponent,
    Spd16ReserveRiskComponent,
    Spd16TieBreakComponent,
)
from pyspd.v16.formulation import (
    Spd16PricingEngine,
    Spd16ReportRenderer,
    Spd16ResultSchema,
    Spd16SolvePolicy,
    spd16_formulation,
)


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
    assert Spd16PricingEngine.select_reserve_price(
        island_reserve_mw=0.0,
        definition_dual=99.0,
        requirement_duals=(2.0, 3.5, -0.5),
    ) == 5.0
    assert Spd16PricingEngine.select_reserve_price(
        island_reserve_mw=1.0,
        definition_dual=7.0,
        requirement_duals=(2.0, 3.5),
    ) == 7.0

