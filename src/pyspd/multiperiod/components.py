"""Class-owned Pyomo components for the multi-period battery profile."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuildContext, ModelComponent
from pyspd.multiperiod.data import (
    MULTIPERIOD_BATTERY_FORMULATION_ID,
    MultiPeriodCase,
)

_SUPPORTED = frozenset({MULTIPERIOD_BATTERY_FORMULATION_ID})


def _data(context: BuildContext) -> MultiPeriodCase:
    if not isinstance(context.case_data, MultiPeriodCase):
        raise TypeError("multi-period components require MultiPeriodCase")
    return context.case_data


class MultiPeriodDomainsComponent(ModelComponent):
    name = "multiperiod_domains"
    supported_formulations = _SUPPORTED
    provides = frozenset({"multiperiod_data", "time_domains"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        block = pyo.Block(concrete=True)
        context.model.add_component("TimeDomains", block)
        block.Period = pyo.Set(initialize=data.period_ids, ordered=True)
        block.DurationHours = pyo.Param(
            block.Period,
            initialize={
                period.period_id: period.duration_hours for period in data.periods
            },
        )
        block.DemandMW = pyo.Param(
            block.Period,
            initialize={period.period_id: period.demand_mw for period in data.periods},
        )
        context.model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
        return {"multiperiod_data": data, "time_domains": block}


class MultiPeriodGenerationComponent(ModelComponent):
    name = "multiperiod_generation"
    supported_formulations = _SUPPORTED
    requires = frozenset({"multiperiod_data", "time_domains"})
    provides = frozenset({"generation", "offer_cost"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        block = pyo.Block(concrete=True)
        context.model.add_component("Generation", block)
        keys = tuple((offer.period_id, offer.generator_id) for offer in data.offers)
        limits = {
            (offer.period_id, offer.generator_id): offer.capacity_mw
            for offer in data.offers
        }
        costs = {
            (offer.period_id, offer.generator_id): offer.price_per_mwh
            for offer in data.offers
        }
        block.Offer = pyo.Set(dimen=2, initialize=keys, ordered=True)
        block.DispatchMW = pyo.Var(
            block.Offer,
            domain=pyo.NonNegativeReals,
            bounds=lambda _block, period, generator: (
                0.0,
                limits[(period, generator)],
            ),
        )
        return {"generation": block.DispatchMW, "offer_cost": costs}


class MultiPeriodBatteryComponent(ModelComponent):
    name = "multiperiod_battery"
    supported_formulations = _SUPPORTED
    requires = frozenset({"multiperiod_data", "time_domains"})
    provides = frozenset(
        {
            "battery_charge",
            "battery_discharge",
            "battery_energy",
            "battery_power_limit",
            "storage_balance",
            "storage_terminal",
        }
    )

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["time_domains"]
        block = pyo.Block(concrete=True)
        context.model.add_component("Battery", block)
        batteries = {battery.battery_id: battery for battery in data.batteries}
        block.Battery = pyo.Set(initialize=tuple(batteries), ordered=True)
        block.ChargeMW = pyo.Var(
            domains.Period,
            block.Battery,
            domain=pyo.NonNegativeReals,
            bounds=lambda _block, _period, battery: (
                0.0,
                batteries[battery].power_capacity_mw,
            ),
        )
        block.DischargeMW = pyo.Var(
            domains.Period,
            block.Battery,
            domain=pyo.NonNegativeReals,
            bounds=lambda _block, _period, battery: (
                0.0,
                batteries[battery].power_capacity_mw,
            ),
        )
        block.EnergyMWh = pyo.Var(
            domains.Period,
            block.Battery,
            domain=pyo.NonNegativeReals,
            bounds=lambda _block, _period, battery: (
                0.0,
                batteries[battery].energy_capacity_mwh,
            ),
        )
        period_ids = data.period_ids
        predecessor = {
            period: (None if index == 0 else period_ids[index - 1])
            for index, period in enumerate(period_ids)
        }

        def storage_rule(_block: pyo.Block, period: str, battery_id: str) -> Any:
            battery = batteries[battery_id]
            previous = predecessor[period]
            starting_energy: Any = (
                battery.initial_energy_mwh
                if previous is None
                else block.EnergyMWh[previous, battery_id]
            )
            duration = domains.DurationHours[period]
            return block.EnergyMWh[period, battery_id] == starting_energy + duration * (
                battery.charge_efficiency * block.ChargeMW[period, battery_id]
                - block.DischargeMW[period, battery_id] / battery.discharge_efficiency
            )

        block.StorageBalance = pyo.Constraint(
            domains.Period, block.Battery, rule=storage_rule
        )
        block.PowerLimit = pyo.Constraint(
            domains.Period,
            block.Battery,
            rule=lambda _block, period, battery: (
                block.ChargeMW[period, battery] + block.DischargeMW[period, battery]
                <= batteries[battery].power_capacity_mw
            ),
        )
        last_period = period_ids[-1]
        block.TerminalEnergy = pyo.Constraint(
            block.Battery,
            rule=lambda _block, battery: (
                block.EnergyMWh[last_period, battery]
                == batteries[battery].terminal_energy_mwh
            ),
        )
        return {
            "battery_charge": block.ChargeMW,
            "battery_discharge": block.DischargeMW,
            "battery_energy": block.EnergyMWh,
            "battery_power_limit": block.PowerLimit,
            "storage_balance": block.StorageBalance,
            "storage_terminal": block.TerminalEnergy,
        }


class MultiPeriodBalanceComponent(ModelComponent):
    name = "multiperiod_balance"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "battery_charge",
            "battery_discharge",
            "generation",
            "multiperiod_data",
            "time_domains",
        }
    )
    provides = frozenset({"energy_balance"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["time_domains"]
        generation = context.artifacts["generation"]
        charge = context.artifacts["battery_charge"]
        discharge = context.artifacts["battery_discharge"]
        block = pyo.Block(concrete=True)
        context.model.add_component("EnergyBalance", block)
        generators_by_period = {
            period: tuple(
                offer.generator_id for offer in data.offers if offer.period_id == period
            )
            for period in data.period_ids
        }
        battery_ids = tuple(battery.battery_id for battery in data.batteries)
        block.Balance = pyo.Constraint(
            domains.Period,
            rule=lambda _block, period: (
                sum(
                    generation[period, generator]
                    for generator in generators_by_period[period]
                )
                + sum(discharge[period, battery] for battery in battery_ids)
                == domains.DemandMW[period]
                + sum(charge[period, battery] for battery in battery_ids)
            ),
        )
        return {"energy_balance": block.Balance}


class MultiPeriodObjectiveComponent(ModelComponent):
    name = "multiperiod_objective"
    supported_formulations = _SUPPORTED
    requires = frozenset(
        {
            "battery_charge",
            "battery_discharge",
            "generation",
            "multiperiod_data",
            "offer_cost",
            "time_domains",
        }
    )
    provides = frozenset({"system_objective"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        data = _data(context)
        domains = context.artifacts["time_domains"]
        generation = context.artifacts["generation"]
        offer_cost = context.artifacts["offer_cost"]
        charge = context.artifacts["battery_charge"]
        discharge = context.artifacts["battery_discharge"]
        block = pyo.Block(concrete=True)
        context.model.add_component("SystemObjective", block)
        batteries = {battery.battery_id: battery for battery in data.batteries}
        block.TotalCost = pyo.Objective(
            expr=sum(
                domains.DurationHours[period]
                * offer_cost[(period, generator)]
                * generation[period, generator]
                for period, generator in generation
            )
            + sum(
                domains.DurationHours[period]
                * batteries[battery].throughput_cost_per_mwh
                * (charge[period, battery] + discharge[period, battery])
                for period in domains.Period
                for battery in batteries
            ),
            sense=pyo.minimize,
        )
        return {"system_objective": block.TotalCost}
