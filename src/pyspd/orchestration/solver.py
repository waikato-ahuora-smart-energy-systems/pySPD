"""Gate 8 case executor and bounded energy-shortfall re-solve loop."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol

import pyomo.environ as pyo

from pyspd.architecture import Formulation, ModelAssembler, PricingEngine
from pyspd.preprocess.shortfall import ShortfallTransferResolver, ShortfallTransferState
from pyspd.reserve import ReserveCase, ReservePricingEngine, reserve_formulation
from pyspd.v16.data import Spd16Case
from pyspd.v16.formulation import Spd16PricingEngine, spd16_formulation

from .types import Key, PreparedCase, SolveObservation


class CaseExecutor(Protocol):
    def solve(self, prepared: PreparedCase) -> SolveObservation: ...


@dataclass(frozen=True, slots=True)
class ShortfallTransition:
    solve_loop: int
    transfers: Mapping[tuple[Key, Key], float]
    scaling_disabled: frozenset[Key]
    untransferred: frozenset[Key]


@dataclass(frozen=True, slots=True)
class ShortfallLoopResult:
    prepared: PreparedCase
    accepted: SolveObservation
    solve_count: int
    transitions: tuple[ShortfallTransition, ...]
    transfers: Mapping[tuple[Key, Key], float]
    untransferred: frozenset[Key]
    limit_reached: bool


class ShortfallLoop:
    """Compose solve observations with the Gate 3 transfer resolver."""

    def __init__(self, executor: CaseExecutor, *, tolerance: float = 1e-9) -> None:
        self.executor = executor
        self.tolerance = float(tolerance)
        self.resolver = ShortfallTransferResolver()

    def run(self, prepared: PreparedCase, *, maximum_loops: int) -> ShortfallLoopResult:
        limit = prepared.maximum_solve_loops or maximum_loops
        limit = min(limit, maximum_loops)
        current = prepared
        transitions: list[ShortfallTransition] = []
        all_transfers: dict[tuple[Key, Key], float] = defaultdict(float)
        all_untransferred: set[Key] = set()
        accepted: SolveObservation | None = None
        for solve_loop in range(1, limit + 1):
            accepted = self.executor.solve(current)
            if not current.transfer_enabled:
                return self._result(
                    current,
                    accepted,
                    solve_loop,
                    transitions,
                    all_transfers,
                    all_untransferred,
                    False,
                )
            shortfall = {
                key: value
                for key, value in accepted.energy_shortfall.items()
                if value > self.tolerance
                and key not in current.load_override_nodes
                and key not in current.instructed_shed_nodes
            }
            if not shortfall:
                return self._result(
                    current,
                    accepted,
                    solve_loop,
                    transitions,
                    all_transfers,
                    all_untransferred,
                    False,
                )
            # The pinned vSPD shortfall branch is guarded by LoopCount <
            # maxSolveLoops. Never mutate load or report a transition after the
            # final accepted solve because that state was not re-solved.
            if solve_loop >= limit:
                return self._result(
                    current,
                    accepted,
                    solve_loop,
                    transitions,
                    all_transfers,
                    all_untransferred,
                    True,
                )
            dead = _dead_nodes(accepted, self.tolerance)
            eligible = {
                node
                for node in shortfall
                if node in current.potential_inconsistency_nodes
                or not current.use_actual_load
                or node in current.load_bad_nodes
                or node in dead
            }
            adjustments = {
                node: value
                + (0.0 if node in dead else current.shortfall_removal_margin)
                for node, value in shortfall.items()
                if node in eligible
            }
            ineligible = set(shortfall) - eligible
            newly_disabled = ineligible - set(current.scaling_disabled_nodes)
            if not adjustments and not newly_disabled:
                return self._result(
                    current,
                    accepted,
                    solve_loop,
                    transitions,
                    all_transfers,
                    all_untransferred,
                    False,
                )
            state = ShortfallTransferState(
                required_load=current.required_load,
                adjustment_mw=adjustments,
                energy_shortfall_mw=accepted.energy_shortfall,
                dead_nodes=frozenset(dead),
                load_override_nodes=current.load_override_nodes,
                instructed_shed_nodes=current.instructed_shed_nodes,
                electrical_island=accepted.node_electrical_island,
            )
            resolved = self.resolver.resolve(current.node_transfer, state)
            for key, value in resolved.transfers.items():
                all_transfers[key] += value
            all_untransferred.update(resolved.untransferred)
            transitions.append(
                ShortfallTransition(
                    solve_loop,
                    resolved.transfers,
                    frozenset(newly_disabled),
                    resolved.untransferred,
                )
            )
            current = replace(
                current,
                required_load=resolved.required_load,
                scaling_disabled_nodes=frozenset(
                    set(current.scaling_disabled_nodes) | newly_disabled
                ),
            )
        assert accepted is not None
        return self._result(
            current,
            accepted,
            limit,
            transitions,
            all_transfers,
            all_untransferred,
            True,
        )

    @staticmethod
    def _result(
        prepared: PreparedCase,
        accepted: SolveObservation,
        solve_count: int,
        transitions: list[ShortfallTransition],
        transfers: Mapping[tuple[Key, Key], float],
        untransferred: set[Key],
        limit_reached: bool,
    ) -> ShortfallLoopResult:
        return ShortfallLoopResult(
            prepared,
            accepted,
            solve_count,
            tuple(transitions),
            dict(transfers),
            frozenset(untransferred),
            limit_reached,
        )


class ReserveCaseExecutor:
    """Execute a prepared case through Gate 7 SCIP→fixed-discrete→HiGHS."""

    def solve(self, prepared: PreparedCase) -> SolveObservation:
        if not isinstance(prepared.payload, ReserveCase):
            raise TypeError("ReserveCaseExecutor requires a ReserveCase payload")
        case = _updated_case(prepared)
        built = ModelAssembler().assemble(self.formulation(), case)
        outcome = built.formulation.solve_policy().solve(built)
        prices = self.pricing_engine().price(built, outcome)
        primary = outcome.primary_model
        generation = _values(primary.artifacts["generation"])
        scarcity = _values(primary.artifacts["energy_scarcity_node"])
        network = case.network
        assert network is not None
        bus_generation: dict[Key, float] = defaultdict(float)
        for ca, dt, offer, node in network.offer_node:
            for key, weight in network.node_bus_allocation.items():
                if key[:3] == (ca, dt, node):
                    bus_generation[(ca, dt, key[3])] += weight * generation.get(
                        (ca, dt, offer), 0.0
                    )
        bus_load: dict[Key, float] = defaultdict(float)
        for key, weight in network.node_bus_allocation.items():
            bus_load[(key[0], key[1], key[3])] += weight * network.node_load[key[:3]]
        node_island = {
            node: min(
                (
                    network.bus_electrical_island.get((*node[:2], key[3]), 0.0)
                    for key in network.node_bus
                    if key[:3] == node
                ),
                default=0.0,
            )
            for node in case.nodes
        }
        adjacency = frozenset(
            ((*branch[:2], left), (*branch[:2], right))
            for branch in network.branches
            for *prefix, left in network.branch_from_bus
            for *other_prefix, right in network.branch_to_bus
            if tuple(prefix) == branch and tuple(other_prefix) == branch
        )
        flow = _values(primary.artifacts["directed_branch_flow"])
        connected_flow: dict[Key, float] = defaultdict(float)
        for branch in network.ac_branches:
            buses = [key[3] for key in network.branch_bus_connect if key[:3] == branch]
            amount = sum(value for key, value in flow.items() if key[:3] == branch)
            for bus in buses:
                connected_flow[(*branch[:2], bus)] += amount
        generation_block = _values(primary.artifacts["generation_block"])
        cleared: dict[Key, float] = defaultdict(float)
        for block, amount in generation_block.items():
            if amount <= 0.0:
                continue
            offer_key = block[:3]
            for ca, dt, mapped_offer, node in network.offer_node:
                if (ca, dt, mapped_offer) != offer_key:
                    continue
                for key in network.node_bus:
                    if key[:3] == (ca, dt, node):
                        bus_key = (ca, dt, key[3])
                        cleared[bus_key] = max(
                            cleared[bus_key], case.offer_price[block]
                        )
        reserve_prices = {key: value for key, value in prices.reserve.items()}
        return SolveObservation(
            generation={key[2]: value for key, value in generation.items()},
            energy_shortfall=scarcity,
            bus_generation=bus_generation,
            bus_load=bus_load,
            raw_bus_prices=prices.energy.raw_bus_duals,
            reserve_prices=reserve_prices,
            node_bus_allocation=network.node_bus_allocation,
            bus_electrical_island=network.bus_electrical_island,
            node_electrical_island=node_island,
            node_market_island={
                node: case.node_region[node][2] for node in case.nodes
            },
            node_transfer=prepared.node_transfer,
            bus_adjacency=adjacency,
            connected_bus_flow=connected_flow,
            cleared_offer_price=cleared,
            sos_price_repair_required=bool(outcome.detected_issues),
            objective=outcome.primary_snapshot.objective,
            solve_payload=outcome,
        )

    def formulation(self) -> Formulation:
        return reserve_formulation()

    def pricing_engine(self) -> PricingEngine:
        return ReservePricingEngine()


class Spd16CaseExecutor(ReserveCaseExecutor):
    """Execute an SPD v16 case through the same qualified solver state machine."""

    def solve(self, prepared: PreparedCase) -> SolveObservation:
        if not isinstance(prepared.payload, Spd16Case):
            raise TypeError("Spd16CaseExecutor requires a Spd16Case payload")
        return super().solve(prepared)

    def formulation(self) -> Formulation:
        return spd16_formulation()

    def pricing_engine(self) -> PricingEngine:
        return Spd16PricingEngine()


def _updated_case(prepared: PreparedCase) -> ReserveCase:
    case = prepared.payload
    assert isinstance(case, ReserveCase)
    assert case.network is not None
    network = replace(case.network, node_load=prepared.required_load)
    required_by_region: dict[Key, float] = defaultdict(float)
    for node, value in prepared.required_load.items():
        required_by_region[case.node_region[node]] += value
    generation_start = dict(case.generation_start)
    for offer in case.offers:
        if offer[2] in prepared.generation_start:
            generation_start[offer] = prepared.generation_start[offer[2]]
    scarcity_limit = dict(case.scarcity_limit)
    for block in case.scarcity_blocks:
        node = block[:3]
        old = case.network.node_load.get(node, 0.0)
        if old > 0.0:
            scarcity_limit[block] *= prepared.required_load.get(node, old) / old
    return replace(
        case,
        network=network,
        required_load=required_by_region,
        generation_start=generation_start,
        scarcity_limit=scarcity_limit,
    )


def _values(component: Any) -> dict[Key, float]:
    return {
        tuple(index): float(pyo.value(component[index], exception=False) or 0.0)
        for index in component
    }


def _dead_nodes(observation: SolveObservation, tolerance: float) -> set[Key]:
    island_load: dict[tuple[str, str, float], float] = defaultdict(float)
    island_generation: dict[tuple[str, str, float], float] = defaultdict(float)
    for bus in observation.raw_bus_prices:
        island = observation.bus_electrical_island.get(bus, 0.0)
        identity = (bus[0], bus[1], island)
        island_load[identity] += observation.bus_load.get(bus, 0.0)
        island_generation[identity] += observation.bus_generation.get(bus, 0.0)
    disconnected = {
        bus
        for bus in observation.raw_bus_prices
        if (
            observation.bus_electrical_island.get(bus, 0.0) == 0.0
            and abs(observation.bus_load.get(bus, 0.0)) <= tolerance
        )
        or abs(
            island_load[
                (
                    bus[0],
                    bus[1],
                    observation.bus_electrical_island.get(bus, 0.0),
                )
            ]
        )
        <= tolerance
        or abs(
            island_generation[
                (
                    bus[0],
                    bus[1],
                    observation.bus_electrical_island.get(bus, 0.0),
                )
            ]
        )
        <= tolerance
    }
    return {
        node
        for node in observation.node_electrical_island
        if observation.node_electrical_island.get(node, 0.0) == 0.0
        or sum(
            weight
            for key, weight in observation.node_bus_allocation.items()
            if key[:3] == node and key[:2] + (key[3],) not in disconnected
        )
        <= tolerance
    }
