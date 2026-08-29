"""vSPD bus/node price repair, allocation, and publication services."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping

from .types import (
    CaseRunResult,
    OrchestrationError,
    PriceTrace,
    PublishedPrices,
    SolveObservation,
)

type Key = tuple[str, ...]


class MarketPricePostProcessor:
    """Keep raw, repaired, and node prices as separately auditable layers."""

    def __init__(
        self,
        *,
        deficit_penalty: float = 500_000.0,
        surplus_penalty: float = 500_000.0,
        bad_price_factor: float = 5.0,
        maximum_scarcity_price: float = 20_000.0,
        tolerance: float = 1e-9,
    ) -> None:
        if (
            min(
                deficit_penalty,
                surplus_penalty,
                bad_price_factor,
                maximum_scarcity_price,
            )
            <= 0.0
        ):
            raise OrchestrationError("price-processing limits must be positive")
        self.deficit_penalty = float(deficit_penalty)
        self.surplus_penalty = float(surplus_penalty)
        self.bad_price_factor = float(bad_price_factor)
        self.maximum_scarcity_price = float(maximum_scarcity_price)
        self.tolerance = float(tolerance)

    def process(
        self,
        observation: SolveObservation,
        *,
        price_transfer_enabled: bool,
    ) -> PriceTrace:
        raw = dict(observation.raw_bus_prices)
        repaired = dict(raw)
        disconnected = self._disconnected(observation)
        for bus in raw:
            load = observation.bus_load.get(bus, 0.0)
            electrical_island = observation.bus_electrical_island.get(bus, 0.0)
            if electrical_island == 0.0 and load > 0.0:
                repaired[bus] = self.deficit_penalty
            elif electrical_island == 0.0 and load < 0.0:
                repaired[bus] = -self.surplus_penalty
            if bus in disconnected:
                repaired[bus] = 0.0
        invalid: set[Key] = set()
        if observation.sos_price_repair_required:
            invalid = self._invalid(observation, repaired, disconnected, initial=True)
            previous_count = len(invalid) + 1
            while invalid and len(invalid) < previous_count:
                previous_count = len(invalid)
                replacements: dict[Key, float] = {}
                for bus in sorted(invalid):
                    neighbours = {
                        right if left == bus else left
                        for left, right in observation.bus_adjacency
                        if bus in {left, right}
                        and (right if left == bus else left) not in invalid
                    }
                    if neighbours:
                        replacements[bus] = sum(
                            repaired[neighbour] for neighbour in neighbours
                        ) / len(neighbours)
                repaired.update(replacements)
                invalid = self._invalid(
                    observation, repaired, disconnected, initial=False
                )
        node_prices = self._allocate_nodes(observation, repaired)
        dead_nodes = {
            node
            for node in observation.node_electrical_island
            if sum(
                weight
                for key, weight in observation.node_bus_allocation.items()
                if key[:3] == node and key[:2] + (key[3],) not in disconnected
            )
            == 0.0
        }
        sources: dict[Key, Key] = {}
        if price_transfer_enabled and dead_nodes:
            self._transfer_dead_prices(
                node_prices,
                dead_nodes,
                sources,
                observation.node_transfer,
                observation.node_electrical_island,
            )
        return PriceTrace(
            raw_bus=raw,
            repaired_bus=repaired,
            node=node_prices,
            reserve=observation.reserve_prices,
            disconnected_buses=frozenset(disconnected),
            dead_nodes=frozenset(dead_nodes),
            dead_node_price_source=sources,
            invalid_buses=frozenset(invalid),
        )

    def _disconnected(self, observation: SolveObservation) -> set[Key]:
        island_load: dict[tuple[str, str, float], float] = defaultdict(float)
        for bus in observation.raw_bus_prices:
            island = observation.bus_electrical_island.get(bus, 0.0)
            island_load[(bus[0], bus[1], island)] += observation.bus_load.get(bus, 0.0)
        return {
            bus
            for bus in observation.raw_bus_prices
            if (
                observation.bus_electrical_island.get(bus, 0.0) == 0.0
                and _zero(observation.bus_load.get(bus, 0.0), self.tolerance)
            )
            or (
                observation.bus_electrical_island.get(bus, 0.0) > 0.0
                and _zero(
                    island_load[
                        (
                            bus[0],
                            bus[1],
                            observation.bus_electrical_island.get(bus, 0.0),
                        )
                    ],
                    self.tolerance,
                )
            )
        }

    def _invalid(
        self,
        observation: SolveObservation,
        prices: dict[Key, float],
        disconnected: set[Key],
        *,
        initial: bool,
    ) -> set[Key]:
        invalid: set[Key] = set()
        for bus, price in prices.items():
            if bus in disconnected:
                continue
            balanced = math.isclose(
                observation.bus_load.get(bus, 0.0),
                observation.bus_generation.get(bus, 0.0),
                abs_tol=self.tolerance,
            )
            no_flow = _zero(
                observation.connected_bus_flow.get(bus, 0.0), self.tolerance
            )
            has_connection = any(bus in edge for edge in observation.bus_adjacency)
            if not (balanced and no_flow and has_connection):
                continue
            cleared = observation.cleared_offer_price.get(bus, 0.0)
            if initial:
                suspicious = (
                    _zero(price, self.tolerance)
                    or abs(price) > self.bad_price_factor * self.maximum_scarcity_price
                    or math.isclose(price, cleared, abs_tol=self.tolerance)
                    or math.isclose(price, cleared + 0.0005, abs_tol=self.tolerance)
                    or math.isclose(price, cleared - 0.0005, abs_tol=self.tolerance)
                )
            else:
                suspicious = (
                    _zero(price, self.tolerance)
                    or price > 0.9 * self.deficit_penalty
                    or price < -0.9 * self.surplus_penalty
                )
            if suspicious:
                invalid.add(bus)
        return invalid

    @staticmethod
    def _allocate_nodes(
        observation: SolveObservation, prices: dict[Key, float]
    ) -> dict[Key, float]:
        output = dict.fromkeys(observation.node_electrical_island, 0.0)
        for key, weight in observation.node_bus_allocation.items():
            node = key[:3]
            bus = key[:2] + (key[3],)
            output[node] = output.get(node, 0.0) + weight * prices.get(bus, 0.0)
        return output

    @staticmethod
    def _transfer_dead_prices(
        node_prices: dict[Key, float],
        dead_nodes: set[Key],
        sources: dict[Key, Key],
        mappings: tuple[tuple[Key, Key], ...],
        islands: Mapping[Key, float],
    ) -> None:
        island_map: dict[Key, float] = dict(islands)
        remaining = set(dead_nodes)
        for _iteration in range(len(remaining) + 1):
            changed = False
            for target, candidate in mappings:
                if target not in remaining or candidate in remaining:
                    continue
                if island_map.get(target, 0.0) not in {
                    0.0,
                    island_map.get(candidate, 0.0),
                }:
                    continue
                node_prices[target] = node_prices.get(candidate, 0.0)
                sources[target] = candidate
                remaining.remove(target)
                changed = True
            if not changed:
                break


class PublishedPriceAggregator:
    """Aggregate case prices using authoritative per-case publication seconds."""

    def aggregate(
        self, cases: tuple[CaseRunResult, ...], *, decimals: int
    ) -> PublishedPrices:
        energy_numerator: dict[tuple[str, str], float] = defaultdict(float)
        reserve_numerator: dict[tuple[str, str, str], float] = defaultdict(float)
        totals: dict[str, float] = defaultdict(float)
        for result in cases:
            seconds = result.specification.publication_seconds
            if seconds <= 0.0 or result.prices is None:
                continue
            period = result.specification.trading_period
            totals[period] += seconds
            for node, price in result.prices.node.items():
                energy_numerator[(period, node[2])] += price * seconds
            for key, price in result.prices.reserve.items():
                reserve_numerator[(period, key[2], key[3])] += price * seconds
        energy = {
            key: round(value / totals[key[0]], decimals)
            for key, value in energy_numerator.items()
            if totals[key[0]] > 0.0
        }
        reserve = {
            key: round(value / totals[key[0]], decimals)
            for key, value in reserve_numerator.items()
            if totals[key[0]] > 0.0
        }
        return PublishedPrices(energy, reserve, totals)


def _zero(value: float, tolerance: float) -> bool:
    return abs(value) <= tolerance
