"""Immutable data contracts for the multi-period battery research profile."""

from __future__ import annotations

import math
from dataclasses import dataclass

MULTIPERIOD_BATTERY_FORMULATION_ID = "pyspd-multiperiod-battery-v1"


class MultiPeriodDataError(ValueError):
    """Multi-period source data is incomplete or physically impossible."""


@dataclass(frozen=True, slots=True)
class Period:
    period_id: str
    duration_hours: float
    demand_mw: float


@dataclass(frozen=True, slots=True)
class PeriodOffer:
    period_id: str
    generator_id: str
    capacity_mw: float
    price_per_mwh: float


@dataclass(frozen=True, slots=True)
class BatteryAsset:
    battery_id: str
    power_capacity_mw: float
    energy_capacity_mwh: float
    initial_energy_mwh: float
    terminal_energy_mwh: float
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0
    throughput_cost_per_mwh: float = 0.0


@dataclass(frozen=True, slots=True)
class MultiPeriodCase:
    case_id: str
    periods: tuple[Period, ...]
    offers: tuple[PeriodOffer, ...]
    batteries: tuple[BatteryAsset, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise MultiPeriodDataError("case ID must not be empty")
        if not self.periods:
            raise MultiPeriodDataError("at least one period is required")
        period_ids = tuple(period.period_id for period in self.periods)
        if any(not value.strip() for value in period_ids):
            raise MultiPeriodDataError("period IDs must not be empty")
        if len(set(period_ids)) != len(period_ids):
            raise MultiPeriodDataError("period IDs must be unique")
        for period in self.periods:
            if not math.isfinite(period.duration_hours) or period.duration_hours <= 0.0:
                raise MultiPeriodDataError(
                    "period duration must be finite and positive"
                )
            if not math.isfinite(period.demand_mw) or period.demand_mw < 0.0:
                raise MultiPeriodDataError(
                    "period demand must be finite and nonnegative"
                )

        offer_keys: set[tuple[str, str]] = set()
        for offer in self.offers:
            if offer.period_id not in period_ids:
                raise MultiPeriodDataError(
                    f"offer references unknown period {offer.period_id!r}"
                )
            if not offer.generator_id.strip():
                raise MultiPeriodDataError("generator ID must not be empty")
            key = (offer.period_id, offer.generator_id)
            if key in offer_keys:
                raise MultiPeriodDataError("period/generator offers must be unique")
            offer_keys.add(key)
            if not math.isfinite(offer.capacity_mw) or offer.capacity_mw < 0.0:
                raise MultiPeriodDataError(
                    "offer capacity must be finite and nonnegative"
                )
            if not math.isfinite(offer.price_per_mwh):
                raise MultiPeriodDataError("offer price must be finite")

        battery_ids: set[str] = set()
        for battery in self.batteries:
            if not battery.battery_id.strip():
                raise MultiPeriodDataError("battery ID must not be empty")
            if battery.battery_id in battery_ids:
                raise MultiPeriodDataError("battery IDs must be unique")
            battery_ids.add(battery.battery_id)
            if (
                not math.isfinite(battery.power_capacity_mw)
                or battery.power_capacity_mw <= 0.0
            ):
                raise MultiPeriodDataError(
                    "battery power capacity must be finite and positive"
                )
            if (
                not math.isfinite(battery.energy_capacity_mwh)
                or battery.energy_capacity_mwh <= 0.0
            ):
                raise MultiPeriodDataError(
                    "battery energy capacity must be finite and positive"
                )
            for label, value in (
                ("initial energy", battery.initial_energy_mwh),
                ("terminal energy", battery.terminal_energy_mwh),
            ):
                if (
                    not math.isfinite(value)
                    or not 0.0 <= value <= battery.energy_capacity_mwh
                ):
                    raise MultiPeriodDataError(
                        f"battery {label} must lie within energy capacity"
                    )
            for label, value in (
                ("charge efficiency", battery.charge_efficiency),
                ("discharge efficiency", battery.discharge_efficiency),
            ):
                if not math.isfinite(value) or not 0.0 < value <= 1.0:
                    raise MultiPeriodDataError(f"battery {label} must lie in (0, 1]")
            if (
                not math.isfinite(battery.throughput_cost_per_mwh)
                or battery.throughput_cost_per_mwh < 0.0
            ):
                raise MultiPeriodDataError(
                    "battery throughput cost must be finite and nonnegative"
                )

    @property
    def period_ids(self) -> tuple[str, ...]:
        return tuple(period.period_id for period in self.periods)
