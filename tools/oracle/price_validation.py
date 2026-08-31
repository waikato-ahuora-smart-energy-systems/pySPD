"""Solver-independent node-price and finite-difference validation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar


@dataclass(frozen=True)
class NodeBusAllocation:
    node: str
    bus: str
    factor: float


class NodePriceMapper:
    def map_prices(
        self,
        bus_prices: Mapping[str, float],
        allocations: Sequence[NodeBusAllocation],
        allocation_tolerance: float = 1e-10,
    ) -> dict[str, float]:
        seen: set[tuple[str, str]] = set()
        totals: dict[str, float] = {}
        prices: dict[str, float] = {}
        for allocation in allocations:
            key = (allocation.node, allocation.bus)
            if key in seen:
                raise ValueError(f"duplicate node/bus allocation: {key!r}")
            seen.add(key)
            if allocation.bus not in bus_prices:
                raise ValueError(f"missing bus price for {allocation.bus!r}")
            if not math.isfinite(allocation.factor) or allocation.factor < 0:
                raise ValueError(f"invalid allocation factor: {allocation!r}")
            bus_price = float(bus_prices[allocation.bus])
            if not math.isfinite(bus_price):
                raise ValueError(f"non-finite bus price for {allocation.bus!r}")
            totals[allocation.node] = (
                totals.get(allocation.node, 0.0) + allocation.factor
            )
            prices[allocation.node] = (
                prices.get(allocation.node, 0.0) + allocation.factor * bus_price
            )
        invalid = {
            node: total
            for node, total in totals.items()
            if abs(total - 1.0) > allocation_tolerance
        }
        if invalid:
            raise ValueError(f"node allocation factors do not sum to one: {invalid}")
        if not prices:
            raise ValueError("no node/bus allocations supplied")
        return prices


@dataclass(frozen=True)
class FiniteDifferenceCheck:
    observed_price: float
    expected_price: float
    absolute_delta: float
    threshold: float
    passed: bool

    @classmethod
    def for_maximum_net_benefit(
        cls,
        objective_minus: float,
        objective_plus: float,
        perturbation_mw: float,
        expected_price: float,
        absolute_tolerance: float = 0.001,
        relative_tolerance: float = 1e-8,
    ) -> FiniteDifferenceCheck:
        if not math.isfinite(perturbation_mw) or perturbation_mw <= 0:
            raise ValueError("perturbation_mw must be positive and finite")
        observed = (objective_minus - objective_plus) / (2.0 * perturbation_mw)
        delta = abs(observed - expected_price)
        threshold = absolute_tolerance + relative_tolerance * max(
            abs(observed), abs(expected_price)
        )
        return cls(
            observed_price=observed,
            expected_price=expected_price,
            absolute_delta=delta,
            threshold=threshold,
            passed=math.isfinite(observed) and delta <= threshold,
        )


@dataclass(frozen=True)
class PriceDelta:
    key: tuple[str, ...]
    expected: float
    actual: float
    absolute_delta: float
    passed: bool


@dataclass(frozen=True)
class PriceComparison:
    deltas: tuple[PriceDelta, ...]

    @property
    def passed(self) -> bool:
        return bool(self.deltas) and all(delta.passed for delta in self.deltas)

    @property
    def max_absolute_delta(self) -> float:
        return max(delta.absolute_delta for delta in self.deltas)

    @property
    def worst_key(self) -> tuple[str, ...]:
        return max(self.deltas, key=lambda delta: delta.absolute_delta).key

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "max_absolute_delta": self.max_absolute_delta,
            "worst_key": self.worst_key,
            "deltas": [asdict(delta) for delta in self.deltas],
        }


class PriceComparator:
    @staticmethod
    def compare(
        actual: Mapping[tuple[str, ...], float],
        expected: Mapping[tuple[str, ...], float],
        absolute_tolerance: float = 0.001,
        relative_tolerance: float = 1e-8,
    ) -> PriceComparison:
        if set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            raise ValueError(f"price keys differ; missing={missing}, extra={extra}")
        deltas = []
        for key in sorted(expected):
            actual_value = float(actual[key])
            expected_value = float(expected[key])
            if not math.isfinite(actual_value) or not math.isfinite(expected_value):
                raise ValueError(f"non-finite price for {key!r}")
            delta = abs(actual_value - expected_value)
            threshold = absolute_tolerance + relative_tolerance * max(
                abs(actual_value), abs(expected_value)
            )
            deltas.append(
                PriceDelta(
                    key=key,
                    expected=expected_value,
                    actual=actual_value,
                    absolute_delta=delta,
                    passed=delta <= threshold,
                )
            )
        return PriceComparison(deltas=tuple(deltas))


@dataclass(frozen=True)
class IndependentPriceValidation:
    active_scenario: str
    price_count: int
    native_comparison: PriceComparison
    report_comparison: PriceComparison | None
    bus_price_adjustment_count: int = 0
    price_transfer_count: int = 0

    @property
    def passed(self) -> bool:
        return self.native_comparison.passed and (
            self.report_comparison is None or self.report_comparison.passed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_scenario": self.active_scenario,
            "price_count": self.price_count,
            "bus_price_adjustment_count": self.bus_price_adjustment_count,
            "price_transfer_count": self.price_transfer_count,
            "passed": self.passed,
            "native_comparison": self.native_comparison.to_dict(),
            "report_comparison": (
                self.report_comparison.to_dict()
                if self.report_comparison is not None
                else None
            ),
        }


class IndependentPriceValidator:
    """Derive node prices from balance marginals without vSPD price parameters."""

    def validate(
        self,
        bus_marginals: Mapping[tuple[str, str, str], float],
        allocations: Mapping[tuple[str, str, str, str], float],
        native_prices: Mapping[tuple[str, str, str, str], float],
        active_scenario: str,
        report_prices: Mapping[tuple[str, str, str], float] | None,
        native_absolute_tolerance: float = 1e-9,
        report_absolute_tolerance: float = 0.0005,
        mapped_bus_prices: Mapping[tuple[str, str, str], float] | None = None,
        bus_price_adjustment_count: int = 0,
        price_transfer_periods: AbstractSet[tuple[str, str]] = frozenset(),
        disconnected_buses: AbstractSet[tuple[str, str, str]] = frozenset(),
        node_links: AbstractSet[tuple[str, str, str, str]] = frozenset(),
        node_islands: AbstractSet[tuple[str, str, str, str]] = frozenset(),
    ) -> IndependentPriceValidation:
        active_native: dict[tuple[str, ...], float] = {
            key: value
            for key, value in native_prices.items()
            if key[2] == active_scenario
        }
        if not active_native:
            raise ValueError(
                f"no native prices for active scenario {active_scenario!r}"
            )
        allocations_by_node: dict[
            tuple[str, str, str], list[NodeBusAllocation]
        ] = {}
        for (ca, dt, node, bus), factor in allocations.items():
            allocations_by_node.setdefault((ca, dt, node), []).append(
                NodeBusAllocation(node=node, bus=bus, factor=float(factor))
            )
        price_source = (
            mapped_bus_prices if mapped_bus_prices is not None else bus_marginals
        )
        bus_prices_by_period: dict[tuple[str, str], dict[str, float]] = {}
        for (ca, dt, bus), price in price_source.items():
            bus_prices_by_period.setdefault((ca, dt), {})[bus] = float(price)
        calculated: dict[tuple[str, ...], float] = {}
        expected_nodes = {(ca, dt, node) for ca, dt, _, node in active_native}
        for ca, dt, node in sorted(expected_nodes):
            mapped = NodePriceMapper().map_prices(
                bus_prices_by_period.get((ca, dt), {}),
                allocations_by_node.get((ca, dt, node), ()),
            )
            calculated[(ca, dt, active_scenario, node)] = mapped[node]
        price_transfer_count = self._apply_dead_node_price_transfer(
            calculated=calculated,
            active_scenario=active_scenario,
            allocations=allocations,
            price_transfer_periods=price_transfer_periods,
            disconnected_buses=disconnected_buses,
            node_links=node_links,
            node_islands=node_islands,
        )
        native_comparison = PriceComparator.compare(
            calculated,
            active_native,
            absolute_tolerance=native_absolute_tolerance,
            relative_tolerance=1e-12,
        )
        calculated_report: dict[tuple[str, ...], float] = {
            (dt, scenario, node): value
            for (_, dt, scenario, node), value in calculated.items()
        }
        report_comparison: PriceComparison | None = None
        if report_prices is not None:
            active_report: dict[tuple[str, ...], float] = {
                key: value
                for key, value in report_prices.items()
                if key[1] == active_scenario
            }
            unknown_report_keys = set(active_report) - set(calculated_report)
            if unknown_report_keys:
                raise ValueError(
                    "report prices are outside the calculated price universe: "
                    f"{sorted(unknown_report_keys)}"
                )
            report_comparison = PriceComparator.compare(
                {key: calculated_report[key] for key in active_report},
                active_report,
                absolute_tolerance=report_absolute_tolerance,
                relative_tolerance=1e-12,
            )
        return IndependentPriceValidation(
            active_scenario=active_scenario,
            price_count=len(calculated),
            native_comparison=native_comparison,
            report_comparison=report_comparison,
            bus_price_adjustment_count=bus_price_adjustment_count,
            price_transfer_count=price_transfer_count,
        )

    @staticmethod
    def _apply_dead_node_price_transfer(
        calculated: dict[tuple[str, ...], float],
        active_scenario: str,
        allocations: Mapping[tuple[str, str, str, str], float],
        price_transfer_periods: AbstractSet[tuple[str, str]],
        disconnected_buses: AbstractSet[tuple[str, str, str]],
        node_links: AbstractSet[tuple[str, str, str, str]],
        node_islands: AbstractSet[tuple[str, str, str, str]],
    ) -> int:
        nodes_by_period: dict[tuple[str, str], set[str]] = {}
        for ca, dt, scenario, node in calculated:
            if scenario == active_scenario:
                nodes_by_period.setdefault((ca, dt), set()).add(node)
        islands_by_period_node: dict[tuple[str, str, str], set[str]] = {}
        for ca, dt, node, island in node_islands:
            islands_by_period_node.setdefault((ca, dt, node), set()).add(island)
        connected_allocation_by_node: dict[tuple[str, str, str], float] = {}
        for (ca, dt, node, bus), factor in allocations.items():
            if (ca, dt, bus) not in disconnected_buses:
                key = (ca, dt, node)
                connected_allocation_by_node[key] = (
                    connected_allocation_by_node.get(key, 0.0) + float(factor)
                )
        links_by_source: dict[tuple[str, str, str], set[str]] = {}
        for ca, dt, source, target in node_links:
            links_by_source.setdefault((ca, dt, source), set()).add(target)

        transfer_count = 0
        for ca, dt in sorted(price_transfer_periods):
            nodes = nodes_by_period.get((ca, dt), set())
            islands_by_node = {
                node: islands_by_period_node.get((ca, dt, node), set())
                for node in nodes
            }
            dead_nodes = {
                node
                for node in nodes
                if connected_allocation_by_node.get((ca, dt, node), 0.0) == 0.0
            }
            while dead_nodes:
                sources_by_node = {
                    node: {
                        target
                        for target in links_by_source.get((ca, dt, node), set())
                        if target not in dead_nodes
                        and islands_by_node.get(node, set())
                        & islands_by_node.get(target, set())
                    }
                    for node in dead_nodes
                }
                transferable = {
                    node: sources
                    for node, sources in sources_by_node.items()
                    if sources
                }
                if not transferable:
                    break
                replacements = {
                    node: sum(
                        calculated[(ca, dt, active_scenario, source)]
                        for source in sources
                    )
                    for node, sources in transferable.items()
                }
                for node, price in replacements.items():
                    calculated[(ca, dt, active_scenario, node)] = price
                dead_nodes -= transferable.keys()
                transfer_count += len(transferable)
        return transfer_count


class GdxPriceValidator:
    """Adapt the canonical vSPD pricing-solution GDX to the independent validator."""

    _required: ClassVar[set[str]] = {
        "drs",
        "pyspd_active_drs_ord",
        "nodeBusAllocationFactor",
        "ACnodeNetInjectionDefinition2",
        "o_drsnodeprice",
    }

    def __init__(self, system_directory: Path | None = None) -> None:
        self.system_directory = system_directory

    def validate(
        self,
        solution_gdx: Path,
        report_prices: Mapping[tuple[str, str, str], float],
    ) -> IndependentPriceValidation:
        try:
            import gams.transfer as gt  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError(
                "GDX price validation requires the uv oracle dependency group"
            ) from error
        container = gt.Container(
            system_directory=(
                str(self.system_directory)
                if self.system_directory is not None
                else None
            )
        )
        container.read(str(solution_gdx))
        names = set(container.listSymbols())
        missing = sorted(self._required - names)
        if missing:
            raise ValueError(f"pricing GDX is missing symbols: {missing}")
        scenarios = tuple(
            str(record[0])
            for record in container["drs"].records.itertuples(index=False)
        )
        active_ordinal = round(
            float(container["pyspd_active_drs_ord"].records.iloc[0]["value"])
        )
        if active_ordinal < 1 or active_ordinal > len(scenarios):
            raise ValueError(
                f"invalid active demand scenario ordinal: {active_ordinal}"
            )
        active_scenario = scenarios[active_ordinal - 1]
        balance = container["ACnodeNetInjectionDefinition2"].records
        allocations = container["nodeBusAllocationFactor"].records
        native = container["o_drsnodeprice"].records
        return IndependentPriceValidator().validate(
            bus_marginals={
                (str(row.ca), str(row.dt), str(row.b)): float(row.marginal)
                for row in balance.itertuples(index=False)
            },
            allocations={
                (str(row.ca), str(row.dt), str(row.n), str(row.b)): float(row.value)
                for row in allocations.itertuples(index=False)
            },
            native_prices={
                (str(row.ca), str(row.dt), str(row.drs), str(row.n)): float(row.value)
                for row in native.itertuples(index=False)
            },
            active_scenario=active_scenario,
            report_prices=report_prices,
        )


class GdxPublishedPriceValidator:
    """Validate normal/AUD prices from balance marginals and published CSV data."""

    _required: ClassVar[set[str]] = {
        "nodeBusAllocationFactor",
        "ACnodeNetInjectionDefinition2",
        "busPrice",
        "busDisconnected",
        "dtParameter",
        "node2node",
        "nodeIsland",
        "o_nodePrice_TP",
        "studyMode",
    }

    def __init__(self, system_directory: Path | None = None) -> None:
        self.system_directory = system_directory

    def validate(
        self,
        solution_gdx: Path,
        report_prices: Mapping[tuple[str, str], float] | None,
    ) -> IndependentPriceValidation:
        try:
            import gams.transfer as gt  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError(
                "GDX price validation requires the uv oracle dependency group"
            ) from error
        container = gt.Container(
            system_directory=(
                str(self.system_directory)
                if self.system_directory is not None
                else None
            )
        )
        container.read(str(solution_gdx))
        names = set(container.listSymbols())
        missing = sorted(self._required - names)
        if missing:
            raise ValueError(f"pricing GDX is missing symbols: {missing}")
        balance = container["ACnodeNetInjectionDefinition2"].records
        postprocessed_bus = container["busPrice"].records
        allocations = container["nodeBusAllocationFactor"].records
        native = container["o_nodePrice_TP"].records
        date_time_parameters = {
            (str(ca), str(date_time), str(parameter)): float(value)
            for ca, date_time, parameter, value in container[
                "dtParameter"
            ].records.itertuples(index=False, name=None)
        }
        study_modes = {
            (str(ca), str(date_time)): round(float(value))
            for ca, date_time, value in container["studyMode"].records.itertuples(
                index=False, name=None
            )
        }
        price_transfer_periods = frozenset(
            period
            for period, mode in study_modes.items()
            if mode in {101, 130, 131, 201}
            and date_time_parameters.get((*period, "priceTransfer"), 0.0) != 0.0
        )
        bus_marginals = {
            (str(row.ca), str(row.dt), str(row.b)): float(row.marginal)
            for row in balance.itertuples(index=False)
        }
        sparse_bus_prices = {
            (str(row.ca), str(row.dt), str(row.b)): float(row.value)
            for row in postprocessed_bus.itertuples(index=False)
        }
        unknown_bus_prices = set(sparse_bus_prices) - set(bus_marginals)
        if unknown_bus_prices:
            raise ValueError(
                "postprocessed bus prices are outside the balance universe: "
                f"{sorted(unknown_bus_prices)}"
            )
        mapped_bus_prices = {
            key: sparse_bus_prices.get(key, 0.0) for key in bus_marginals
        }
        adjustment_count = sum(
            not math.isclose(
                mapped_bus_prices[key],
                marginal,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
            for key, marginal in bus_marginals.items()
        )
        allocation_values = {
            (str(row.ca), str(row.dt), str(row.n), str(row.b)): float(row.value)
            for row in allocations.itertuples(index=False)
        }
        sparse_native = {
            (str(row.ca), str(row.dt), str(row.n)): float(row.value)
            for row in native.itertuples(index=False)
        }
        node_universe = {
            (ca, date_time, node)
            for ca, date_time, node, _ in allocation_values
        }
        unknown_native = set(sparse_native) - node_universe
        if unknown_native:
            raise ValueError(
                "native node prices are outside the allocation universe: "
                f"{sorted(unknown_native)}"
            )
        return IndependentPriceValidator().validate(
            bus_marginals=bus_marginals,
            mapped_bus_prices=mapped_bus_prices,
            bus_price_adjustment_count=adjustment_count,
            price_transfer_periods=price_transfer_periods,
            disconnected_buses=frozenset(
                (str(ca), str(date_time), str(bus))
                for ca, date_time, bus, value in container[
                    "busDisconnected"
                ].records.itertuples(index=False, name=None)
                if float(value) != 0.0
            ),
            node_links=frozenset(
                (str(ca), str(date_time), str(source), str(target))
                for ca, date_time, source, target, *_ in container[
                    "node2node"
                ].records.itertuples(index=False, name=None)
            ),
            node_islands=frozenset(
                (str(ca), str(date_time), str(node), str(island))
                for ca, date_time, node, island, *_ in container[
                    "nodeIsland"
                ].records.itertuples(index=False, name=None)
            ),
            allocations=allocation_values,
            native_prices={
                (ca, date_time, "normal", node): sparse_native.get(
                    (ca, date_time, node), 0.0
                )
                for ca, date_time, node in node_universe
            },
            active_scenario="normal",
            report_prices=(
                {
                    (date_time, "normal", node): price
                    for (date_time, node), price in report_prices.items()
                }
                if report_prices is not None
                else None
            ),
            report_absolute_tolerance=5e-6,
        )
