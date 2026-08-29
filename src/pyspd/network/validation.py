"""Independent Gate 5 flow, loss, security, rental, and price validation."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import BuiltModel, ModelAssembler
from pyspd.network.data import NetworkCase, NetworkData
from pyspd.network.formulation import (
    NetworkPrices,
    NetworkPricingEngine,
    ac_network_formulation,
)

type Key = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NetworkValidationReport:
    residuals: dict[str, float]
    rentals: dict[Key, float]
    tolerance: float
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "residuals", MappingProxyType(dict(self.residuals)))
        object.__setattr__(self, "rentals", MappingProxyType(dict(self.rentals)))


@dataclass(frozen=True, slots=True)
class NodalPriceCheck:
    node: Key
    reported_price: float
    finite_difference_price: float
    absolute_error: float
    perturbation_mw: float
    passed: bool


def _value(component: Any, key: Key) -> float:
    value = pyo.value(component[key], exception=False)
    return 0.0 if value is None else float(value)


class IndependentNetworkValidator:
    """Recompute network identities without evaluating Pyomo constraints."""

    def validate(
        self,
        built_model: BuiltModel,
        prices: NetworkPrices,
        *,
        tolerance: float = 1e-7,
    ) -> NetworkValidationReport:
        case = built_model.case_data
        if not isinstance(case, NetworkCase) or case.network is None:
            raise TypeError("network validation requires NetworkCase")
        data = case.network
        a = built_model.artifacts
        residuals: dict[str, float] = {}

        flow = a["branch_flow"]
        directed = a["directed_branch_flow"]
        losses = a["directed_branch_loss"]
        flow_block = a["branch_flow_block"]
        loss_block = a["branch_loss_block"]
        angle = a["node_angle"]
        injection = a["net_injection"]
        generation = a["generation"]
        purchase = a["purchase"]
        scarcity = a["energy_scarcity_node"]
        deficit = a["balance_deficit"]
        surplus = a["balance_surplus"]
        branch_surplus = a["branch_flow_surplus"]

        for branch in data.ac_branches:
            forward = _value(directed, (*branch, "forward"))
            backward = _value(directed, (*branch, "backward"))
            residuals[f"flow_definition:{branch}"] = abs(
                _value(flow, branch) - forward + backward
            )
            from_bus = _endpoint(data.branch_from_bus, branch)
            to_bus = _endpoint(data.branch_to_bus, branch)
            dc_flow = data.branch_susceptance[branch] * (
                _value(angle, (*branch[:2], from_bus))
                - _value(angle, (*branch[:2], to_bus))
            )
            residuals[f"dc_flow:{branch}"] = abs(_value(flow, branch) - dc_flow)
            for direction in ("forward", "backward"):
                segment_keys = [
                    key
                    for key in data.valid_ac_loss_segments
                    if key[:3] == branch and key[4] == direction
                ]
                residuals[f"directed_composition:{branch}:{direction}"] = abs(
                    _value(directed, (*branch, direction))
                    - sum(_value(flow_block, key) for key in segment_keys)
                )
                residuals[f"loss_composition:{branch}:{direction}"] = abs(
                    _value(losses, (*branch, direction))
                    - sum(_value(loss_block, key) for key in segment_keys)
                )
                for key in segment_keys:
                    residuals[f"loss_segment:{key}"] = abs(
                        _value(loss_block, key)
                        - data.ac_loss_segment_factor[key] * _value(flow_block, key)
                    )
                    residuals[f"loss_segment_limit:{key}"] = max(
                        0.0,
                        _value(flow_block, key) - data.ac_loss_segment_mw[key],
                    )
                if data.use_ac_branch_limits:
                    residuals[f"capacity:{branch}:{direction}"] = max(
                        0.0,
                        _value(directed, (*branch, direction))
                        - _value(branch_surplus, branch)
                        - data.branch_capacity[(*branch, direction)],
                    )

        for bus in data.buses:
            ca, dt, bus_id = bus
            outgoing = sum(
                _value(directed, (*branch, direction))
                for branch in data.ac_branches
                for direction in ("forward", "backward")
                if _sending(data, branch, bus, direction)
            )
            incoming = sum(
                _value(directed, (*branch, direction))
                for branch in data.ac_branches
                for direction in ("forward", "backward")
                if _receiving(data, branch, bus, direction)
            )
            residuals[f"bus_flow_balance:{bus}"] = abs(
                _value(injection, bus) - outgoing + incoming
            )
            supply = sum(
                data.node_bus_allocation.get((ca, dt, node, bus_id), 0.0)
                * _value(generation, (ca, dt, offer))
                for o_ca, o_dt, offer, node in data.offer_node
                if (o_ca, o_dt) == (ca, dt)
                and (ca, dt, node, bus_id) in data.node_bus
            )
            demand_bid = sum(
                data.node_bus_allocation.get((ca, dt, node, bus_id), 0.0)
                * _value(purchase, (ca, dt, bid))
                for b_ca, b_dt, bid, node in data.bid_node
                if (b_ca, b_dt) == (ca, dt)
                and (ca, dt, node, bus_id) in data.node_bus
            )
            load = sum(
                data.node_bus_allocation.get((ca, dt, node, bus_id), 0.0)
                * data.node_load[(ca, dt, node)]
                for n_ca, n_dt, node, n_bus in data.node_bus
                if (n_ca, n_dt, n_bus) == bus
            )
            dynamic_loss = sum(
                (
                    data.receiving_end_loss_proportion
                    if _receiving(data, branch, bus, direction)
                    else 1.0 - data.receiving_end_loss_proportion
                )
                * _value(losses, (*branch, direction))
                for branch in data.ac_branches
                for direction in ("forward", "backward")
                if _receiving(data, branch, bus, direction)
                or _sending(data, branch, bus, direction)
            )
            fixed_loss = sum(
                0.5 * data.branch_fixed_loss[branch]
                for branch in data.branches
                if (*branch, bus_id) in data.branch_bus_connect
            )
            scarcity_supply = sum(
                data.node_bus_allocation.get((ca, dt, node, bus_id), 0.0)
                * _value(scarcity, (ca, dt, node))
                for n_ca, n_dt, node, n_bus in data.node_bus
                if (n_ca, n_dt, n_bus) == bus
            )
            resource = (
                supply
                - demand_bid
                - load
                - dynamic_loss
                - fixed_loss
                + _value(deficit, bus)
                - _value(surplus, bus)
                + scarcity_supply
            )
            residuals[f"bus_resource_balance:{bus}"] = abs(
                _value(injection, bus) - resource
            )

        branch_deficit = a["branch_constraint_deficit"]
        branch_constraint_surplus = a["branch_constraint_surplus"]
        for key in data.branch_constraints:
            ca, dt, constraint = key
            lhs = sum(
                data.branch_constraint_factor.get(
                    (ca, dt, constraint, branch), 0.0
                )
                * _value(flow, (ca, dt, branch))
                for b_ca, b_dt, branch in data.ac_branches
                if (b_ca, b_dt) == (ca, dt)
            )
            sense = data.branch_constraint_sense[key]
            lhs += _value(branch_deficit, key) if sense >= 0.0 else 0.0
            lhs -= (
                _value(branch_constraint_surplus, key) if sense <= 0.0 else 0.0
            )
            residuals[f"branch_security:{key}"] = _sense_residual(
                lhs, data.branch_constraint_limit[key], sense
            )

        market_deficit = a["market_node_constraint_deficit"]
        market_surplus = a["market_node_constraint_surplus"]
        for key in data.market_node_constraints:
            ca, dt, constraint = key
            lhs = sum(
                data.market_node_energy_offer_factor.get(
                    (ca, dt, constraint, offer), 0.0
                )
                * _value(generation, (ca, dt, offer))
                for o_ca, o_dt, offer in data.positive_offers
                if (o_ca, o_dt) == (ca, dt)
            ) + sum(
                data.market_node_energy_bid_factor.get(
                    (ca, dt, constraint, bid), 0.0
                )
                * _value(purchase, (ca, dt, bid))
                for b_ca, b_dt, bid in case.bids
                if (b_ca, b_dt) == (ca, dt)
            )
            sense = data.market_node_constraint_sense[key]
            lhs += _value(market_deficit, key) if sense >= 0.0 else 0.0
            lhs -= _value(market_surplus, key) if sense <= 0.0 else 0.0
            residuals[f"market_node_security:{key}"] = _sense_residual(
                lhs, data.market_node_constraint_limit[key], sense
            )

        rentals = branch_rentals(built_model, prices)
        passed = all(math.isfinite(value) and value <= tolerance for value in residuals.values())
        return NetworkValidationReport(residuals, rentals, tolerance, passed)


def branch_rentals(
    built_model: BuiltModel, prices: NetworkPrices
) -> dict[Key, float]:
    case = built_model.case_data
    if not isinstance(case, NetworkCase) or case.network is None:
        raise TypeError("rental calculation requires NetworkCase")
    data = case.network
    flow_component = built_model.artifacts["branch_flow"]
    loss_component = built_model.artifacts["directed_branch_loss"]
    rentals: dict[Key, float] = {}
    for branch in data.ac_branches:
        from_bus = (*branch[:2], _endpoint(data.branch_from_bus, branch))
        to_bus = (*branch[:2], _endpoint(data.branch_to_bus, branch))
        flow = _value(flow_component, branch)
        dynamic_loss = sum(
            _value(loss_component, (*branch, direction))
            for direction in ("forward", "backward")
        )
        total_loss = dynamic_loss + data.branch_fixed_loss[branch]
        duration = case.interval_minutes[branch[:2]] / 60.0
        if flow >= 0.0:
            rentals[branch] = duration * (
                prices.bus[to_bus] * (flow - total_loss)
                - prices.bus[from_bus] * flow
            )
        else:
            rentals[branch] = duration * (
                prices.bus[to_bus] * flow
                - prices.bus[from_bus] * (flow + total_loss)
            )
    return rentals


def validate_nodal_price_finite_difference(
    case: NetworkCase,
    node: Key,
    *,
    perturbation_mw: float = 1e-4,
    tolerance: float = 1e-3,
) -> NodalPriceCheck:
    if case.network is None:
        raise TypeError("price validation requires NetworkData")
    assembler = ModelAssembler()
    formulation = ac_network_formulation()
    base = assembler.assemble(formulation, case)
    base_solve = formulation.solve_policy().solve(base)
    base_prices = NetworkPricingEngine().price(base, base_solve)
    perturbed_network = case.network.with_node_load(
        node, case.network.node_load[node] + perturbation_mw
    )
    perturbed = assembler.assemble(
        formulation, replace(case, network=perturbed_network)
    )
    formulation.solve_policy().solve(perturbed)
    base_objective = float(pyo.value(base.artifacts["net_benefit"]))
    perturbed_objective = float(pyo.value(perturbed.artifacts["net_benefit"]))
    finite_difference_price = -(
        perturbed_objective - base_objective
    ) / perturbation_mw
    reported = base_prices.node[node]
    error = abs(reported - finite_difference_price)
    return NodalPriceCheck(
        node,
        reported,
        finite_difference_price,
        error,
        perturbation_mw,
        error <= tolerance,
    )


def _endpoint(mappings: frozenset[Key], branch: Key) -> str:
    return next(
        bus
        for ca, dt, candidate, bus in mappings
        if (ca, dt, candidate) == branch
    )


def _sending(
    data: NetworkData, branch: Key, bus: Key, direction: str
) -> bool:
    endpoint = data.branch_from_bus if direction == "forward" else data.branch_to_bus
    return (*branch, bus[2]) in endpoint


def _receiving(
    data: NetworkData, branch: Key, bus: Key, direction: str
) -> bool:
    endpoint = data.branch_to_bus if direction == "forward" else data.branch_from_bus
    return (*branch, bus[2]) in endpoint


def _sense_residual(lhs: float, rhs: float, sense: float) -> float:
    if sense == -1.0:
        return max(0.0, lhs - rhs)
    if sense == 1.0:
        return max(0.0, rhs - lhs)
    return abs(lhs - rhs)
