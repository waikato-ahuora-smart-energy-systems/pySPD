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
        reserve_sum: dict[tuple[str, str, str], float] = defaultdict(float)
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
                else:
                    expected = sum(
                        weight * prices.repaired_bus.get((key[0], key[1], key[3]), 0.0)
                        for key, weight in observation.node_bus_allocation.items()
                        if key[:3] == node
                    )
                error = abs(actual - expected)
                errors.append(error)
                if error > tolerance:
                    failures.append(f"node allocation mismatch: {node}")
            seconds = result.specification.publication_seconds
            if seconds <= 0.0:
                continue
            period = result.specification.trading_period
            seconds_sum[period] += seconds
            for node, price in prices.node.items():
                energy_sum[(period, node[2])] += price * seconds
            for key, price in prices.reserve.items():
                reserve_sum[(period, key[2], key[3])] += price * seconds
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
        if set(expected_energy) != set(published.energy):
            failures.append("published energy identity set mismatch")
        if set(expected_reserve) != set(published.reserve):
            failures.append("published reserve identity set mismatch")
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
        if any(not math.isfinite(value) for value in errors):
            failures.append("non-finite validation residual")
        return PublicationValidation(
            not failures,
            len(errors),
            max(errors, default=0.0),
            tuple(failures),
        )
