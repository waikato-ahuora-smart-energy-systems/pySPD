"""Independent Gate 8 price-allocation and publication recomputation."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from .types import CaseRunResult, PublishedPrices


@dataclass(frozen=True, slots=True)
class PublicationValidation:
    passed: bool
    check_count: int
    maximum_absolute_error: float
    failures: tuple[str, ...]


class IndependentPublicationValidator:
    """Recompute published identities without invoking production processors."""

    def validate(
        self,
        cases: tuple[CaseRunResult, ...],
        published: PublishedPrices,
        *,
        tolerance: float = 1e-6,
        decimals: int = 5,
    ) -> PublicationValidation:
        failures: list[str] = []
        errors: list[float] = []
        energy_sum: dict[tuple[str, str], float] = defaultdict(float)
        energy_lower_sum: dict[tuple[str, str], float] = defaultdict(float)
        energy_upper_sum: dict[tuple[str, str], float] = defaultdict(float)
        energy_interval_keys: set[tuple[str, str]] = set()
        reserve_sum: dict[tuple[str, str, str], float] = defaultdict(float)
        reserve_lower_sum: dict[tuple[str, str, str], float] = defaultdict(float)
        reserve_upper_sum: dict[tuple[str, str, str], float] = defaultdict(float)
        reserve_interval_keys: set[tuple[str, str, str]] = set()
        seconds_sum: dict[str, float] = defaultdict(float)
        for result in cases:
            if result.prices is None or result.accepted is None:
                continue
            prices = result.prices
            observation = result.accepted
            for bus in prices.disconnected_buses:
                error = abs(prices.repaired_bus[bus])
                errors.append(error)
                if error > tolerance:
                    failures.append(f"disconnected bus price is nonzero: {bus}")
            for node, actual in prices.node.items():
                if node in prices.dead_node_price_source:
                    source = prices.dead_node_price_source[node]
                    expected = prices.node[source]
                    expected_interval = prices.node_intervals.get(source)
                else:
                    expected = sum(
                        weight * prices.repaired_bus.get((key[0], key[1], key[3]), 0.0)
                        for key, weight in observation.node_bus_allocation.items()
                        if key[:3] == node
                    )
                    lower = 0.0
                    upper = 0.0
                    has_interval = False
                    for key, weight in observation.node_bus_allocation.items():
                        if key[:3] != node:
                            continue
                        bus = (key[0], key[1], key[3])
                        price = prices.repaired_bus.get(bus, 0.0)
                        bounds = prices.repaired_bus_intervals.get(
                            bus, (price, price)
                        )
                        has_interval = has_interval or (
                            bus in prices.repaired_bus_intervals
                        )
                        if weight >= 0.0:
                            lower += weight * bounds[0]
                            upper += weight * bounds[1]
                        else:
                            lower += weight * bounds[1]
                            upper += weight * bounds[0]
                    expected_interval = (
                        (lower, upper)
                        if has_interval and upper - lower > 1e-9
                        else None
                    )
                error = abs(actual - expected)
                errors.append(error)
                if error > tolerance:
                    failures.append(f"node allocation mismatch: {node}")
                actual_interval = prices.node_intervals.get(node)
                if (actual_interval is None) != (expected_interval is None):
                    failures.append(f"node price interval identity mismatch: {node}")
                elif actual_interval is not None and expected_interval is not None:
                    for actual_bound, expected_bound in zip(
                        actual_interval, expected_interval, strict=True
                    ):
                        interval_error = abs(actual_bound - expected_bound)
                        errors.append(interval_error)
                        if interval_error > tolerance:
                            failures.append(
                                f"node price interval mismatch: {node}"
                            )
            seconds = result.specification.publication_seconds
            if seconds <= 0.0:
                continue
            period = result.specification.trading_period
            seconds_sum[period] += seconds
            for node, price in prices.node.items():
                key = (period, node[2])
                energy_sum[key] += price * seconds
                bounds = prices.node_intervals.get(node, (price, price))
                energy_lower_sum[key] += bounds[0] * seconds
                energy_upper_sum[key] += bounds[1] * seconds
                if node in prices.node_intervals:
                    energy_interval_keys.add(key)
            for key, price in prices.reserve.items():
                published_key = (period, key[2], key[3])
                reserve_sum[published_key] += price * seconds
                bounds = prices.reserve_intervals.get(key, (price, price))
                reserve_lower_sum[published_key] += bounds[0] * seconds
                reserve_upper_sum[published_key] += bounds[1] * seconds
                if key in prices.reserve_intervals:
                    reserve_interval_keys.add(published_key)
        for period, actual in published.total_seconds.items():
            error = abs(actual - seconds_sum[period])
            errors.append(error)
            if error > tolerance:
                failures.append(f"publication seconds mismatch: {period}")
        expected_energy = {
            key: round(value / seconds_sum[key[0]], decimals)
            for key, value in energy_sum.items()
            if seconds_sum[key[0]] > 0.0
        }
        expected_reserve = {
            key: round(value / seconds_sum[key[0]], decimals)
            for key, value in reserve_sum.items()
            if seconds_sum[key[0]] > 0.0
        }
        expected_energy_intervals = {
            key: (
                round(energy_lower_sum[key] / seconds_sum[key[0]], decimals),
                round(energy_upper_sum[key] / seconds_sum[key[0]], decimals),
            )
            for key in energy_interval_keys
            if seconds_sum[key[0]] > 0.0
        }
        expected_reserve_intervals = {
            key: (
                round(reserve_lower_sum[key] / seconds_sum[key[0]], decimals),
                round(reserve_upper_sum[key] / seconds_sum[key[0]], decimals),
            )
            for key in reserve_interval_keys
            if seconds_sum[key[0]] > 0.0
        }
        if set(expected_energy) != set(published.energy):
            failures.append("published energy identity set mismatch")
        if set(expected_reserve) != set(published.reserve):
            failures.append("published reserve identity set mismatch")
        if set(expected_energy_intervals) != set(published.energy_intervals):
            failures.append("published energy interval identity set mismatch")
        if set(expected_reserve_intervals) != set(published.reserve_intervals):
            failures.append("published reserve interval identity set mismatch")
        for key in set(expected_energy) & set(published.energy):
            error = abs(expected_energy[key] - published.energy[key])
            errors.append(error)
            if error > tolerance:
                failures.append(f"published energy mismatch: {key}")
        for key in set(expected_reserve) & set(published.reserve):
            error = abs(expected_reserve[key] - published.reserve[key])
            errors.append(error)
            if error > tolerance:
                failures.append(f"published reserve mismatch: {key}")
        for key in set(expected_energy_intervals) & set(published.energy_intervals):
            for actual_bound, expected_bound in zip(
                published.energy_intervals[key],
                expected_energy_intervals[key],
                strict=True,
            ):
                error = abs(actual_bound - expected_bound)
                errors.append(error)
                if error > tolerance:
                    failures.append(f"published energy interval mismatch: {key}")
        for key in set(expected_reserve_intervals) & set(
            published.reserve_intervals
        ):
            for actual_bound, expected_bound in zip(
                published.reserve_intervals[key],
                expected_reserve_intervals[key],
                strict=True,
            ):
                error = abs(actual_bound - expected_bound)
                errors.append(error)
                if error > tolerance:
                    failures.append(f"published reserve interval mismatch: {key}")
        if any(not math.isfinite(value) for value in errors):
            failures.append("non-finite validation residual")
        return PublicationValidation(
            not failures,
            len(errors),
            max(errors, default=0.0),
            tuple(failures),
        )
