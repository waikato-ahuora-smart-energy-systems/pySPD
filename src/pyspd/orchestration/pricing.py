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
        raw_intervals = dict(observation.raw_bus_price_intervals)
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
        repaired_intervals = {
            bus: bounds
            for bus, bounds in raw_intervals.items()
            if math.isclose(
                repaired.get(bus, math.nan),
                raw[bus],
                rel_tol=0.0,
                abs_tol=self.tolerance,
            )
        }
        node_prices, node_intervals = self._allocate_nodes(
            observation, repaired, repaired_intervals
        )
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
            price_islands: Mapping[Key, float | str] = (
                observation.node_market_island
                if observation.node_market_island
                else observation.node_electrical_island
            )
            self._transfer_dead_prices(
                node_prices,
                node_intervals,
                dead_nodes,
                sources,
                observation.node_transfer,
                price_islands,
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
            raw_bus_intervals=raw_intervals,
            repaired_bus_intervals=repaired_intervals,
            node_intervals=node_intervals,
        )

    def _disconnected(self, observation: SolveObservation) -> set[Key]:
        island_load: dict[tuple[str, str, float], float] = defaultdict(float)
        for bus in observation.raw_bus_prices:
            island = observation.bus_electrical_island.get(bus, 0.0)
            island_load[(bus[0], bus[1], island)] += observation.bus_load.get(bus, 0.0)
        return set(observation.persistent_disconnected_buses) | {
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
        observation: SolveObservation,
        prices: dict[Key, float],
        intervals: Mapping[Key, tuple[float, float]],
    ) -> tuple[dict[Key, float], dict[Key, tuple[float, float]]]:
        output = dict.fromkeys(observation.node_electrical_island, 0.0)
        lower = dict.fromkeys(observation.node_electrical_island, 0.0)
        upper = dict.fromkeys(observation.node_electrical_island, 0.0)
        interval_nodes: set[Key] = set()
        for key, weight in observation.node_bus_allocation.items():
            node = key[:3]
            bus = key[:2] + (key[3],)
            price = prices.get(bus, 0.0)
            output[node] = output.get(node, 0.0) + weight * price
            bounds = intervals.get(bus, (price, price))
            if bus in intervals:
                interval_nodes.add(node)
            if weight >= 0.0:
                lower[node] = lower.get(node, 0.0) + weight * bounds[0]
                upper[node] = upper.get(node, 0.0) + weight * bounds[1]
            else:
                lower[node] = lower.get(node, 0.0) + weight * bounds[1]
                upper[node] = upper.get(node, 0.0) + weight * bounds[0]
        node_intervals = {
            node: (lower[node], upper[node])
            for node in interval_nodes
            if upper[node] - lower[node] > 1e-9
        }
        return output, node_intervals

    @staticmethod
    def _transfer_dead_prices(
        node_prices: dict[Key, float],
        node_intervals: dict[Key, tuple[float, float]],
        dead_nodes: set[Key],
        sources: dict[Key, Key],
        mappings: tuple[tuple[Key, Key], ...],
        islands: Mapping[Key, float | str],
    ) -> None:
        island_map: dict[Key, float | str] = dict(islands)
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
                if candidate in node_intervals:
                    node_intervals[target] = node_intervals[candidate]
                else:
                    node_intervals.pop(target, None)
                sources[target] = candidate
                remaining.remove(target)
                changed = True
            if not changed:
                break


class PublishedPriceAccumulator:
    """Incrementally aggregate authoritative publication weights across a day."""

    def __init__(
        self,
        *,
        energy_numerator: Mapping[tuple[str, str], float] | None = None,
        energy_lower_numerator: Mapping[tuple[str, str], float] | None = None,
        energy_upper_numerator: Mapping[tuple[str, str], float] | None = None,
        energy_interval_keys: frozenset[tuple[str, str]] | None = None,
        reserve_numerator: Mapping[tuple[str, str, str], float] | None = None,
        total_seconds: Mapping[str, float] | None = None,
        date_time: Mapping[str, str] | None = None,
    ) -> None:
        self.energy_numerator: dict[tuple[str, str], float] = defaultdict(float)
        self.energy_numerator.update(energy_numerator or {})
        self.energy_lower_numerator: dict[tuple[str, str], float] = defaultdict(
            float
        )
        self.energy_lower_numerator.update(energy_lower_numerator or {})
        self.energy_upper_numerator: dict[tuple[str, str], float] = defaultdict(
            float
        )
        self.energy_upper_numerator.update(energy_upper_numerator or {})
        self.energy_interval_keys = set(energy_interval_keys or ())
        self.reserve_numerator: dict[tuple[str, str, str], float] = defaultdict(float)
        self.reserve_numerator.update(reserve_numerator or {})
        self.total_seconds: dict[str, float] = defaultdict(float)
        self.total_seconds.update(total_seconds or {})
        self.date_time: dict[str, str] = dict(date_time or {})

    def add(self, result: CaseRunResult) -> None:
        period = result.specification.trading_period
        self.date_time.setdefault(period, result.specification.date_time)
        seconds = result.specification.publication_seconds
        if seconds <= 0.0 or result.prices is None:
            return
        self.total_seconds[period] += seconds
        for node, price in result.prices.node.items():
            key = (period, node[2])
            self.energy_numerator[key] += price * seconds
            bounds = result.prices.node_intervals.get(node, (price, price))
            self.energy_lower_numerator[key] += bounds[0] * seconds
            self.energy_upper_numerator[key] += bounds[1] * seconds
            if node in result.prices.node_intervals:
                self.energy_interval_keys.add(key)
        for reserve_key, price in result.prices.reserve.items():
            self.reserve_numerator[
                (period, reserve_key[2], reserve_key[3])
            ] += price * seconds

    def finish(self, *, decimals: int) -> PublishedPrices:
        energy = {
            key: round(value / self.total_seconds[key[0]], decimals)
            for key, value in self.energy_numerator.items()
            if self.total_seconds[key[0]] > 0.0
        }
        reserve = {
            key: round(value / self.total_seconds[key[0]], decimals)
            for key, value in self.reserve_numerator.items()
            if self.total_seconds[key[0]] > 0.0
        }
        energy_intervals = {
            key: (
                round(
                    self.energy_lower_numerator[key] / self.total_seconds[key[0]],
                    decimals,
                ),
                round(
                    self.energy_upper_numerator[key] / self.total_seconds[key[0]],
                    decimals,
                ),
            )
            for key in self.energy_interval_keys
            if self.total_seconds[key[0]] > 0.0
        }
        return PublishedPrices(
            energy=energy,
            reserve=reserve,
            total_seconds=self.total_seconds,
            date_time=self.date_time,
            energy_intervals=energy_intervals,
        )


class PublishedPriceAggregator:
    """Aggregate case prices using authoritative per-case publication seconds."""

    def aggregate(
        self, cases: tuple[CaseRunResult, ...], *, decimals: int
    ) -> PublishedPrices:
        accumulator = PublishedPriceAccumulator()
        for result in cases:
            accumulator.add(result)
        return accumulator.finish(decimals=decimals)


def _zero(value: float, tolerance: float) -> bool:
    return abs(value) <= tolerance
