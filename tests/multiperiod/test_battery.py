from __future__ import annotations

import math

import pyomo.environ as pyo
import pytest

from pyspd.multiperiod import (
    BatteryAsset,
    BatteryStudyRunner,
    MultiPeriodCase,
    MultiPeriodDataError,
    Period,
    PeriodOffer,
    build_battery_formulation,
)
from pyspd.multiperiod.formulation import MultiPeriodReportRenderer


def _case(*, battery: bool = True) -> MultiPeriodCase:
    return MultiPeriodCase(
        case_id="two-period-arbitrage",
        periods=(
            Period("P1", duration_hours=1.0, demand_mw=0.0),
            Period("P2", duration_hours=1.0, demand_mw=10.0),
        ),
        offers=(
            PeriodOffer("P1", "GEN", capacity_mw=10.0, price_per_mwh=10.0),
            PeriodOffer("P2", "GEN", capacity_mw=10.0, price_per_mwh=100.0),
        ),
        batteries=(
            (
                BatteryAsset(
                    "BAT",
                    power_capacity_mw=10.0,
                    energy_capacity_mwh=10.0,
                    initial_energy_mwh=0.0,
                    terminal_energy_mwh=0.0,
                    charge_efficiency=1.0,
                    discharge_efficiency=1.0,
                ),
            )
            if battery
            else ()
        ),
    )


def test_battery_shifts_low_cost_energy_across_periods() -> None:
    result = BatteryStudyRunner().run(_case())

    assert result.formulation_id == "pyspd-multiperiod-battery-v1"
    assert result.objective_nzd == pytest.approx(100.0)
    assert result.generation_mw[("P1", "GEN")] == pytest.approx(10.0)
    assert result.generation_mw[("P2", "GEN")] == pytest.approx(0.0)
    assert result.charge_mw[("P1", "BAT")] == pytest.approx(10.0)
    assert result.discharge_mw[("P2", "BAT")] == pytest.approx(10.0)
    assert result.energy_mwh[("P1", "BAT")] == pytest.approx(10.0)
    assert result.energy_mwh[("P2", "BAT")] == pytest.approx(0.0)
    assert all(math.isfinite(value) for value in result.energy_prices.values())
    assert max(abs(value) for value in result.balance_residual_mw.values()) < 1e-8
    assert max(abs(value) for value in result.storage_residual_mwh.values()) < 1e-8


def test_no_battery_control_uses_expensive_second_period_generation() -> None:
    result = BatteryStudyRunner().run(_case(battery=False))

    assert result.objective_nzd == pytest.approx(1000.0)
    assert result.generation_mw[("P1", "GEN")] == pytest.approx(0.0)
    assert result.generation_mw[("P2", "GEN")] == pytest.approx(10.0)
    assert dict(result.charge_mw) == {}
    assert dict(result.discharge_mw) == {}
    assert dict(result.energy_mwh) == {}


def test_result_renderer_uses_portable_stable_keys() -> None:
    result = BatteryStudyRunner().run(_case())
    payload = MultiPeriodReportRenderer().render(result)

    assert payload["formulation_id"] == "pyspd-multiperiod-battery-v1"
    assert payload["generation_mw"]["P1|GEN"] == pytest.approx(10.0)
    assert payload["energy_mwh"]["P2|BAT"] == pytest.approx(0.0)
    assert payload["structural_signature"] == result.structural_signature


def test_storage_losses_and_half_hour_duration_are_conserved() -> None:
    case = MultiPeriodCase(
        case_id="lossy-half-hour",
        periods=(Period("P1", 0.5, 0), Period("P2", 0.5, 8)),
        offers=(
            PeriodOffer("P1", "G", 25, 10),
            PeriodOffer("P2", "G", 8, 100),
        ),
        batteries=(
            BatteryAsset(
                "B",
                power_capacity_mw=25,
                energy_capacity_mwh=10,
                initial_energy_mwh=0,
                terminal_energy_mwh=0,
                charge_efficiency=0.8,
                discharge_efficiency=0.8,
            ),
        ),
    )

    result = BatteryStudyRunner().run(case)

    assert result.charge_mw[("P1", "B")] == pytest.approx(12.5)
    assert result.energy_mwh[("P1", "B")] == pytest.approx(5.0)
    assert result.discharge_mw[("P2", "B")] == pytest.approx(8.0)
    assert result.objective_nzd == pytest.approx(62.5)
    assert max(abs(value) for value in result.storage_residual_mwh.values()) < 1e-8


def test_model_is_class_composed_and_repeatably_structured() -> None:
    formulation = build_battery_formulation()
    runner = BatteryStudyRunner(formulation=formulation)
    first = runner.build(_case())
    second = runner.build(_case())

    assert first.formulation is formulation
    assert first.build_order == (
        "multiperiod_domains",
        "multiperiod_battery",
        "multiperiod_generation",
        "multiperiod_balance",
        "multiperiod_objective",
    )
    assert first.structural_signature == second.structural_signature
    assert len(first.structural_signature) == 64
    assert len(tuple(first.model.component_data_objects(pyo.Constraint))) == 7


@pytest.mark.parametrize(
    "asset, message",
    [
        (BatteryAsset("B", 1, 1, 2, 0), "initial energy"),
        (
            BatteryAsset("B", 1, 1, 0, 0, charge_efficiency=1.1),
            "charge efficiency",
        ),
        (BatteryAsset("B", 0, 1, 0, 0), "power capacity"),
    ],
)
def test_battery_data_rejects_impossible_physics(
    asset: BatteryAsset, message: str
) -> None:
    with pytest.raises(MultiPeriodDataError, match=message):
        MultiPeriodCase(
            case_id="bad",
            periods=(Period("P1", 1, 0),),
            offers=(PeriodOffer("P1", "G", 1, 1),),
            batteries=(asset,),
        )


def test_period_order_and_offer_coverage_fail_closed() -> None:
    with pytest.raises(MultiPeriodDataError, match="unique"):
        MultiPeriodCase(
            case_id="duplicate",
            periods=(Period("P1", 1, 0), Period("P1", 1, 0)),
            offers=(PeriodOffer("P1", "G", 1, 1),),
        )
    with pytest.raises(MultiPeriodDataError, match="unknown period"):
        MultiPeriodCase(
            case_id="unknown",
            periods=(Period("P1", 1, 0),),
            offers=(PeriodOffer("P2", "G", 1, 1),),
        )
