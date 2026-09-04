"""Public Gate 5 class-based AC-network formulation profile."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import pyomo.environ as pyo

from pyspd.architecture import (
    BuiltModel,
    Formulation,
    PreprocessorStep,
    PricingEngine,
    ReportRenderer,
    ResultSchema,
    SolvePolicy,
)
from pyspd.contracts import CaseData
from pyspd.core_energy.components import (
    CoreDomainsComponent,
    DemandBidsComponent,
    EnergyOffersComponent,
    EnergyScarcityComponent,
    GenerationRampingComponent,
)
from pyspd.network.components import (
    ACNetworkComponent,
    NetworkDomainsComponent,
    NetworkEconomicsComponent,
    NetworkSecurityComponent,
)
from pyspd.network.data import AC_NETWORK_FORMULATION_ID, NetworkCase
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor
from pyspd.solver import HighsBackend, SolverConfiguration, SolveResult

type Key = tuple[str, ...]

_SUPPORTED = frozenset({AC_NETWORK_FORMULATION_ID})


class NetworkPreprocessor(PreprocessorStep):
    """Project the qualified Gate 3 result and raw nodal mappings immutably."""

    supported_formulations = _SUPPORTED

    def transform(self, case_data: Any) -> NetworkCase:
        if isinstance(case_data, NetworkCase):
            return case_data
        if not isinstance(case_data, CaseData):
            raise TypeError("AC-network preprocessing requires CaseData")
        result = Vspd506Preprocessor(
            PreprocessingSettings(apply_rtd_load_reconstruction=True)
        ).transform(case_data)
        return NetworkCase.from_sources(result, case_data)


class NetworkSolvePolicy(SolvePolicy):
    supported_formulations = _SUPPORTED

    def solve(self, built_model: BuiltModel) -> SolveResult:
        case = built_model.case_data
        if not isinstance(case, NetworkCase) or case.network is None:
            raise TypeError("AC-network solving requires NetworkCase")
        angle = built_model.artifacts["node_angle"]
        for bus in case.network.reference_buses:
            angle[bus].fix(0.0)
        return HighsBackend().solve(
            built_model.model,
            SolverConfiguration(
                {
                    "solver": "simplex",
                    "primal_feasibility_tolerance": 1e-8,
                    "dual_feasibility_tolerance": 1e-8,
                    "random_seed": 0,
                    "threads": 1,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class NetworkPrices:
    bus: Mapping[Key, float]
    node: Mapping[Key, float]
    raw_bus_duals: Mapping[Key, float]
    dead_nodes: frozenset[Key]
    unit: str = "NZD/MWh"
    bus_price_intervals: Mapping[Key, tuple[float, float]] = field(
        default_factory=dict
    )
    node_price_intervals: Mapping[Key, tuple[float, float]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "bus", MappingProxyType(dict(self.bus)))
        object.__setattr__(self, "node", MappingProxyType(dict(self.node)))
        object.__setattr__(
            self, "raw_bus_duals", MappingProxyType(dict(self.raw_bus_duals))
        )
        object.__setattr__(self, "dead_nodes", frozenset(self.dead_nodes))
        object.__setattr__(
            self,
            "bus_price_intervals",
            MappingProxyType(dict(self.bus_price_intervals)),
        )
        object.__setattr__(
            self,
            "node_price_intervals",
            MappingProxyType(dict(self.node_price_intervals)),
        )


class NetworkPricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED

    @staticmethod
    def _loss_kink_leaf_prices(
        built_model: BuiltModel,
        case: NetworkCase,
        prices: Mapping[Key, float],
        *,
        tolerance: float = 1e-7,
    ) -> dict[Key, tuple[float, float]]:
        """Return the analytic dual interval at a radial AC-loss breakpoint.

        When a radial branch flow is exactly the cumulative width of one or
        more loss blocks, either adjacent loss slope is a valid subgradient.
        A leaf without an interior marginal energy variable can therefore take
        either corresponding balance dual.  Exposing both endpoints prevents
        an LP-basis choice from being mistaken for an energy-price mismatch.
        """

        network = case.network
        assert network is not None
        incident: dict[Key, list[Key]] = defaultdict(list)
        for branch in network.ac_branches:
            for key in network.branch_bus_connect:
                if key[:3] == branch:
                    incident[(*branch[:2], key[3])].append(branch)

        artifacts = built_model.artifacts
        directed_flow = artifacts["directed_branch_flow"]
        flow_block = artifacts["branch_flow_block"]
        generation_block = artifacts["generation_block"]
        purchase_block = artifacts["purchase_block"]
        scarcity = artifacts["energy_scarcity_node"]
        deficit = artifacts["balance_deficit"]
        surplus = artifacts["balance_surplus"]
        receiving_share = network.receiving_end_loss_proportion

        def nodes_at(bus: Key) -> set[Key]:
            return {
                (*bus[:2], key[2])
                for key in network.node_bus
                if (*key[:2], key[3]) == bus
                and abs(network.node_bus_allocation.get(key, 0.0)) > tolerance
            }

        def has_interior_marginal(bus: Key) -> bool:
            nodes = nodes_at(bus)
            if (
                abs(float(pyo.value(deficit[bus]))) > tolerance
                or abs(float(pyo.value(surplus[bus]))) > tolerance
                or any(
                    abs(float(pyo.value(scarcity[node]))) > tolerance
                    for node in nodes
                )
            ):
                return True
            for *prefix, offer, node in network.offer_node:
                if tuple(prefix) != bus[:2] or (*prefix, node) not in nodes:
                    continue
                for block_key in case.offer_blocks:
                    if block_key[:3] != (*prefix, offer):
                        continue
                    value = float(pyo.value(generation_block[block_key]))
                    limit = case.offer_limit[block_key]
                    if tolerance < value < limit - tolerance:
                        return True
            for *prefix, bid, node in network.bid_node:
                if tuple(prefix) != bus[:2] or (*prefix, node) not in nodes:
                    continue
                for block_key in case.bid_blocks:
                    if block_key[:3] != (*prefix, bid):
                        continue
                    value = float(pyo.value(purchase_block[block_key]))
                    limit = case.bid_limit[block_key]
                    if tolerance < value < limit - tolerance:
                        return True
            return False

        def ratio(factor: float) -> float | None:
            numerator = 1.0 - receiving_share * factor
            denominator = 1.0 + (1.0 - receiving_share) * factor
            if factor < 0.0 or numerator <= 0.0 or denominator <= 0.0:
                return None
            return numerator / denominator

        intervals: dict[Key, tuple[float, float]] = {}
        for branch in network.ac_branches:
            from_bus_name = next(
                key[3] for key in network.branch_from_bus if key[:3] == branch
            )
            to_bus_name = next(
                key[3] for key in network.branch_to_bus if key[:3] == branch
            )
            from_bus = (*branch[:2], from_bus_name)
            to_bus = (*branch[:2], to_bus_name)
            for direction, sender, receiver in (
                ("forward", from_bus, to_bus),
                ("backward", to_bus, from_bus),
            ):
                active_flow = float(pyo.value(directed_flow[*branch, direction]))
                reverse = "backward" if direction == "forward" else "forward"
                if (
                    active_flow <= tolerance
                    or abs(float(pyo.value(directed_flow[*branch, reverse])))
                    > tolerance
                ):
                    continue
                segments = sorted(
                    (
                        key
                        for key in network.valid_ac_loss_segments
                        if key[:3] == branch and key[4] == direction
                    ),
                    key=lambda key: (network.ac_loss_segment_factor[key], key[3]),
                )
                boundary: tuple[float, float] | None = None
                cumulative = 0.0
                for index, key in enumerate(segments[:-1]):
                    width = network.ac_loss_segment_mw[key]
                    cumulative += width
                    next_key = segments[index + 1]
                    filled = abs(float(pyo.value(flow_block[key])) - width)
                    next_empty = abs(float(pyo.value(flow_block[next_key])))
                    scale = max(1.0, abs(active_flow), abs(cumulative))
                    if (
                        filled <= tolerance * scale
                        and next_empty <= tolerance * scale
                        and abs(active_flow - cumulative) <= tolerance * scale
                    ):
                        boundary = (
                            network.ac_loss_segment_factor[key],
                            network.ac_loss_segment_factor[next_key],
                        )
                        break
                if boundary is None:
                    continue
                radial_leaves = [
                    bus for bus in (sender, receiver) if len(incident[bus]) == 1
                ]
                candidates = (
                    radial_leaves
                    if len(radial_leaves) == 1
                    else [
                        bus
                        for bus in radial_leaves
                        if not has_interior_marginal(bus)
                    ]
                )
                for leaf in candidates:
                    parent = receiver if leaf == sender else sender
                    endpoint_values: list[float] = []
                    for factor in boundary:
                        marginal_ratio = ratio(factor)
                        if marginal_ratio is None:
                            endpoint_values = []
                            break
                        endpoint_values.append(
                            prices[parent] * marginal_ratio
                            if leaf == sender
                            else prices[parent] / marginal_ratio
                        )
                    if len(endpoint_values) != 2:
                        continue
                    bounds = (min(endpoint_values), max(endpoint_values))
                    raw = prices[leaf]
                    endpoint_tolerance = tolerance * max(1.0, abs(raw))
                    if min(abs(raw - value) for value in endpoint_values) <= (
                        endpoint_tolerance
                    ):
                        intervals[leaf] = bounds
        return intervals

    @staticmethod
    def _zero_flow_leaf_prices(
        built_model: BuiltModel,
        case: NetworkCase,
        prices: dict[Key, float],
        *,
        tolerance: float = 1e-9,
    ) -> dict[Key, tuple[float, float]]:
        """Select the export derivative and return the analytic dual interval.

        A passive zero-flow component behind one lossy boundary can have two
        valid LP duals: the derivatives for incremental export and load.
        Historical vSPD/CPLEX result sets select the export-side endpoint for
        WPT1101.  Normalize to that endpoint and propagate it through any
        zero-loss transformer leaves. Positive-loss boundaries anchor the
        recursion.  A passive tree whose multiple live boundaries meet at one
        root retains a solver dual already inside the intersection of the
        boundary intervals. An outlying basis dual is projected to the nearest
        analytic endpoint so the scalar and its certificate remain consistent.
        Unanchored zero-loss cycles retain their solver duals.
        """

        network = case.network
        assert network is not None
        incident: dict[Key, list[Key]] = defaultdict(list)
        for branch in network.ac_branches:
            for key in network.branch_bus_connect:
                if key[:3] == branch:
                    incident[(*branch[:2], key[3])].append(branch)

        branch_flow = built_model.artifacts["branch_flow"]
        directed_flow = built_model.artifacts["directed_branch_flow"]
        net_injection = built_model.artifacts["net_injection"]
        generation = built_model.artifacts["generation"]
        purchase = built_model.artifacts["purchase"]
        scarcity = built_model.artifacts["energy_scarcity_node"]
        deficit = built_model.artifacts["balance_deficit"]
        surplus = built_model.artifacts["balance_surplus"]
        receiving_share = network.receiving_end_loss_proportion
        original = dict(prices)

        def first_factor(branch: Key, direction: str) -> float:
            factors = [
                factor
                for key, factor in network.ac_loss_segment_factor.items()
                if key[:3] == branch and key[4] == direction
            ]
            return min(factors, default=0.0)

        def zero_flow_bus(bus: Key, branches: tuple[Key, ...]) -> bool:
            if network.bus_electrical_island.get(bus, 0.0) == 0.0:
                return False
            return not any(
                abs(float(pyo.value(branch_flow[branch]))) > tolerance
                or abs(network.branch_fixed_loss.get(branch, 0.0)) > tolerance
                or any(
                    abs(float(pyo.value(directed_flow[*branch, direction])))
                    > tolerance
                    for direction in ("forward", "backward")
                )
                for branch in branches
            )

        def passive(bus: Key, branches: tuple[Key, ...]) -> bool:
            if not zero_flow_bus(bus, branches):
                return False
            nodes = {
                (*bus[:2], key[2])
                for key in network.node_bus
                if (*key[:2], key[3]) == bus
                and abs(network.node_bus_allocation.get(key, 0.0)) > tolerance
            }
            if any(
                abs(network.node_load.get(node, 0.0)) > tolerance
                or abs(float(pyo.value(scarcity[node]))) > tolerance
                for node in nodes
            ):
                return False
            if any(
                abs(float(pyo.value(generation[(*prefix, offer)]))) > tolerance
                for *prefix, offer, node in network.offer_node
                if tuple(prefix) == bus[:2] and (*prefix, node) in nodes
            ):
                return False
            return not any(
                abs(float(pyo.value(purchase[(*prefix, bid)]))) > tolerance
                for *prefix, bid, node in network.bid_node
                if tuple(prefix) == bus[:2] and (*prefix, node) in nodes
            )

        endpoints = {
            branch: (
                (*branch[:2], next(
                    key[3]
                    for key in network.branch_from_bus
                    if key[:3] == branch
                )),
                (*branch[:2], next(
                    key[3]
                    for key in network.branch_to_bus
                    if key[:3] == branch
                )),
            )
            for branch in network.ac_branches
        }
        passive_buses = {
            bus
            for bus, raw_branches in incident.items()
            if passive(bus, tuple(raw_branches))
        }
        selected: dict[Key, tuple[Key, Key, float, float]] = {}
        boundary_intervals: dict[Key, tuple[float, float]] = {}
        preserve_scalar: set[Key] = set()

        def edge_factors(bus: Key, branch: Key) -> tuple[float, float] | None:
            from_bus = next(
                key[3] for key in network.branch_from_bus if key[:3] == branch
            )
            to_bus = next(
                key[3] for key in network.branch_to_bus if key[:3] == branch
            )
            if bus[2] == to_bus:
                inward_direction = "forward"
                outward_direction = "backward"
            elif bus[2] == from_bus:
                inward_direction = "backward"
                outward_direction = "forward"
            else:  # pragma: no cover - guarded by the network-data contract
                return None
            return (
                first_factor(branch, inward_direction),
                first_factor(branch, outward_direction),
            )

        def select(bus: Key, branch: Key, parent: Key) -> None:
            factors = edge_factors(bus, branch)
            if factors is None:  # pragma: no cover - guarded above
                return
            inward_factor, outward_factor = factors
            selected[bus] = (
                branch,
                parent,
                inward_factor,
                outward_factor,
            )

        def local_interval(
            parent_price: float,
            inward_factor: float,
            outward_factor: float,
        ) -> tuple[float, float]:
            inward_denominator = 1.0 - receiving_share * inward_factor
            outward_denominator = 1.0 + (
                1.0 - receiving_share
            ) * outward_factor
            if (
                min(inward_factor, outward_factor) < 0.0
                or inward_denominator <= 0.0
                or outward_denominator <= 0.0
            ):
                raise ValueError("AC loss factor makes incremental delivery invalid")
            export_ratio = (
                1.0 - receiving_share * outward_factor
            ) / outward_denominator
            load_ratio = (
                1.0 + (1.0 - receiving_share) * inward_factor
            ) / inward_denominator
            endpoints = (
                parent_price * export_ratio,
                parent_price * load_ratio,
            )
            return min(endpoints), max(endpoints)

        def project(value: float, interval: tuple[float, float]) -> float:
            return min(max(value, interval[0]), interval[1])

        # A passive zero-injection tree has one live boundary. Orient every
        # branch away from that boundary so an export-side choice propagates
        # through chains containing more than one lossy branch. Components
        # with multiple live boundaries or cycles remain solver-selected.
        unvisited = set(passive_buses)
        while unvisited:
            start = min(unvisited)
            component: set[Key] = set()
            pending = [start]
            while pending:
                bus = pending.pop()
                if bus in component:
                    continue
                component.add(bus)
                for branch in incident[bus]:
                    left, right = endpoints[branch]
                    neighbour = right if left == bus else left
                    if neighbour in passive_buses and neighbour not in component:
                        pending.append(neighbour)
            unvisited.difference_update(component)
            internal = {
                branch
                for bus in component
                for branch in incident[bus]
                if all(endpoint in component for endpoint in endpoints[branch])
            }
            boundary = {
                (bus, branch, right if left == bus else left)
                for bus in component
                for branch in incident[bus]
                for left, right in (endpoints[branch],)
                if (right if left == bus else left) not in component
            }
            boundary_roots = {bus for bus, _branch, _parent in boundary}
            if (
                len(boundary) > 1
                and len(internal) == len(component) - 1
                and len(boundary_roots) == 1
            ):
                root = next(iter(boundary_roots))
                candidates = []
                parallel_boundaries: dict[Key, list[Key]] = defaultdict(list)
                for _bus, branch, parent in boundary:
                    parallel_boundaries[parent].append(branch)
                for parent, parallel_branches in parallel_boundaries.items():
                    weighted_factors = []
                    for branch in parallel_branches:
                        factors = edge_factors(root, branch)
                        if factors is None:  # pragma: no cover - guarded above
                            continue
                        weight = abs(float(network.branch_susceptance[branch]))
                        weighted_factors.append((weight, factors))
                    total_weight = sum(weight for weight, _factors in weighted_factors)
                    if total_weight <= tolerance:
                        continue
                    aggregate = tuple(
                        sum(weight * factors[index] for weight, factors in weighted_factors)
                        / total_weight
                        for index in range(2)
                    )
                    candidates.append(local_interval(original[parent], *aggregate))
                if candidates:
                    intersection = (
                        max(bounds[0] for bounds in candidates),
                        min(bounds[1] for bounds in candidates),
                    )
                    if intersection[0] <= intersection[1] + tolerance:
                        boundary_intervals[root] = intersection
                        preserve_scalar.update(component)
                        prices[root] = project(original[root], intersection)
                        root_queue: list[Key] = [root]
                        root_visited: set[Key] = set()
                        while root_queue:
                            bus = root_queue.pop(0)
                            if bus in root_visited:
                                continue
                            root_visited.add(bus)
                            for branch in incident[bus]:
                                left, right = endpoints[branch]
                                child = right if left == bus else left
                                if child in component and child not in root_visited:
                                    select(child, branch, bus)
                                    root_queue.append(child)
                continue
            if len(boundary) != 1 or len(internal) != len(component) - 1:
                continue
            root, root_branch, root_parent = next(iter(boundary))
            queue = [(root, root_branch, root_parent)]
            visited: set[Key] = set()
            while queue:
                bus, branch, parent = queue.pop(0)
                if bus in visited:
                    continue
                visited.add(bus)
                select(bus, branch, parent)
                for child_branch in incident[bus]:
                    left, right = endpoints[child_branch]
                    child = right if left == bus else left
                    if child in component and child not in visited:
                        queue.append((child, child_branch, bus))

        # A leaf can also be locally balanced by fixed/limited generation and
        # equal load. Its net injection and sole branch flow are both zero, so
        # the two one-sided loss derivatives still bound valid balance duals.
        # Preserve the solver scalar, but expose the same analytical interval
        # used for an empty passive leaf. Exclude scarcity, balance slack, and
        # cleared demand bids because those can impose a tighter local bound.
        balanced_leaf_candidates: dict[Key, tuple[Key, Key]] = {}
        for bus, raw_branches in incident.items():
            branches = tuple(raw_branches)
            if (
                bus in passive_buses
                or len(branches) != 1
                or not zero_flow_bus(bus, branches)
                or abs(float(pyo.value(net_injection[bus]))) > tolerance
                or abs(float(pyo.value(deficit[bus]))) > tolerance
                or abs(float(pyo.value(surplus[bus]))) > tolerance
            ):
                continue
            nodes = {
                (*bus[:2], key[2])
                for key in network.node_bus
                if (*key[:2], key[3]) == bus
                and abs(network.node_bus_allocation.get(key, 0.0)) > tolerance
            }
            if any(
                abs(float(pyo.value(scarcity[node]))) > tolerance for node in nodes
            ) or any(
                abs(float(pyo.value(purchase[(*prefix, bid)]))) > tolerance
                for *prefix, bid, node in network.bid_node
                if tuple(prefix) == bus[:2] and (*prefix, node) in nodes
            ):
                continue
            branch = branches[0]
            left, right = endpoints[branch]
            parent = right if left == bus else left
            balanced_leaf_candidates[bus] = (branch, parent)
        for bus, (branch, parent) in balanced_leaf_candidates.items():
            if parent in balanced_leaf_candidates or parent in passive_buses:
                continue
            select(bus, branch, parent)
            preserve_scalar.add(bus)

        memo: dict[Key, float] = {}
        interval_memo: dict[Key, tuple[float, float] | None] = {}

        def cplex_price(bus: Key, visiting: frozenset[Key]) -> float:
            if bus in memo:
                return memo[bus]
            if bus in visiting or bus not in selected:
                return original[bus]
            _branch, parent, inward_factor, outward_factor = selected[bus]
            denominator = 1.0 - receiving_share * outward_factor
            if min(inward_factor, outward_factor) < 0.0 or denominator <= 0.0:
                raise ValueError("AC loss factor makes incremental delivery invalid")
            parent_price = (
                cplex_price(parent, visiting | {bus})
                if parent in selected
                else original[parent]
            )
            value = parent_price * denominator / (
                1.0 + (1.0 - receiving_share) * outward_factor
            )
            memo[bus] = value
            return value

        def analytic_interval(
            bus: Key, visiting: frozenset[Key]
        ) -> tuple[float, float] | None:
            if bus in interval_memo:
                return interval_memo[bus]
            if bus in visiting or bus not in selected:
                return None
            _branch, parent, inward_factor, outward_factor = selected[bus]
            parent_interval = (
                analytic_interval(parent, visiting | {bus})
                if parent in selected
                else boundary_intervals.get(parent)
            )
            if inward_factor == 0.0 and outward_factor == 0.0:
                value = parent_interval
                interval_memo[bus] = value
                return value
            parent_price = cplex_price(parent, visiting | {bus})
            parent_bounds = parent_interval or (parent_price, parent_price)
            endpoints = tuple(
                endpoint
                for bound in parent_bounds
                for endpoint in local_interval(
                    bound, inward_factor, outward_factor
                )
            )
            value = (min(endpoints), max(endpoints))
            interval_memo[bus] = value
            return value

        for bus in selected:
            if bus not in preserve_scalar:
                prices[bus] = cplex_price(bus, frozenset())
            interval = analytic_interval(bus, frozenset())
            if bus in preserve_scalar and interval is not None:
                prices[bus] = project(original[bus], interval)
        intervals = boundary_intervals | {
            bus: interval
            for bus, interval in interval_memo.items()
            if interval is not None and interval[1] - interval[0] > tolerance
        }
        return {
            bus: interval
            for bus, interval in intervals.items()
            if interval[1] - interval[0] > tolerance
        }

    def price(self, built_model: BuiltModel, solve_result: SolveResult) -> NetworkPrices:
        if not solve_result.solution_loaded:
            raise ValueError("pricing requires an optimal loaded LP solution")
        case = built_model.case_data
        if not isinstance(case, NetworkCase) or case.network is None:
            raise TypeError("pricing requires NetworkCase")
        constraints = built_model.artifacts["energy_balance"]
        raw = {
            tuple(index): float(built_model.model.dual[constraints[index]])
            for index in constraints
        }
        bus_intervals = self._zero_flow_leaf_prices(built_model, case, raw)
        bus_intervals.update(
            self._loss_kink_leaf_prices(built_model, case, raw)
        )
        # In ACnodeNetInjectionDefinition2, required load appears with a
        # negative coefficient on the right-hand side.  The equality marginal
        # therefore already has the positive market-price sign used by vSPD.
        bus_prices = dict(raw)
        node_prices: dict[Key, float] = {}
        node_intervals: dict[Key, tuple[float, float]] = {}
        dead: set[Key] = set()
        for node in case.nodes:
            allocations = [
                (key[3], case.network.node_bus_allocation.get(key, 0.0))
                for key in case.network.node_bus
                if key[:3] == node
                and case.network.bus_electrical_island.get(
                    (key[0], key[1], key[3]), 0.0
                )
                != 0.0
            ]
            if not allocations or sum(weight for _bus, weight in allocations) == 0.0:
                dead.add(node)
                node_prices[node] = 0.0
            else:
                node_prices[node] = sum(
                    weight * bus_prices[(node[0], node[1], bus)]
                    for bus, weight in allocations
                )
                lower = 0.0
                upper = 0.0
                has_interval = False
                for bus, weight in allocations:
                    bus_key = (node[0], node[1], bus)
                    bounds = bus_intervals.get(
                        bus_key, (bus_prices[bus_key], bus_prices[bus_key])
                    )
                    has_interval = has_interval or bus_key in bus_intervals
                    if weight >= 0.0:
                        lower += weight * bounds[0]
                        upper += weight * bounds[1]
                    else:
                        lower += weight * bounds[1]
                        upper += weight * bounds[0]
                if has_interval and upper - lower > 1e-9:
                    node_intervals[node] = (lower, upper)
        return NetworkPrices(
            bus=bus_prices,
            node=node_prices,
            raw_bus_duals=raw,
            dead_nodes=frozenset(dead),
            bus_price_intervals=bus_intervals,
            node_price_intervals=node_intervals,
        )


@dataclass(frozen=True, slots=True)
class NetworkResults:
    generation: Mapping[Key, float]
    purchases: Mapping[Key, float]
    branch_flow: Mapping[Key, float]
    directed_flow: Mapping[Key, float]
    directed_loss: Mapping[Key, float]
    deficit: Mapping[Key, float]
    surplus: Mapping[Key, float]
    objective_components: Mapping[str, float]

    def __post_init__(self) -> None:
        for name in (
            "generation",
            "purchases",
            "branch_flow",
            "directed_flow",
            "directed_loss",
            "deficit",
            "surplus",
            "objective_components",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


def _values(component: Any) -> dict[Key, float]:
    output: dict[Key, float] = {}
    for index in component:
        value = pyo.value(component[index], exception=False)
        output[tuple(index)] = 0.0 if value is None else float(value)
    return output


class NetworkResultSchema(ResultSchema):
    supported_formulations = _SUPPORTED

    def collect(self, built_model: BuiltModel, solve_result: SolveResult) -> NetworkResults:
        if not solve_result.solution_loaded:
            raise ValueError("result collection requires a loaded solution")
        artifacts = built_model.artifacts
        return NetworkResults(
            generation=_values(artifacts["generation"]),
            purchases=_values(artifacts["purchase"]),
            branch_flow=_values(artifacts["branch_flow"]),
            directed_flow=_values(artifacts["directed_branch_flow"]),
            directed_loss=_values(artifacts["directed_branch_loss"]),
            deficit=_values(artifacts["balance_deficit"]),
            surplus=_values(artifacts["balance_surplus"]),
            objective_components={
                name: float(pyo.value(artifacts[name]))
                for name in (
                    "system_cost",
                    "system_benefit",
                    "balance_penalty",
                    "ramp_penalty",
                    "movement_cost",
                    "scarcity_cost",
                    "system_penalty",
                    "net_benefit",
                )
            },
        )


class NetworkReportRenderer(ReportRenderer):
    supported_formulations = _SUPPORTED

    def render(self, results: Any) -> Mapping[str, Any]:
        if not isinstance(results, NetworkResults):
            raise TypeError("renderer requires NetworkResults")
        return MappingProxyType(
            {
                "generation_mw": dict(results.generation),
                "purchase_mw": dict(results.purchases),
                "branch_flow_mw": dict(results.branch_flow),
                "branch_directional_flow_mw": dict(results.directed_flow),
                "branch_directional_loss_mw": dict(results.directed_loss),
                "bus_deficit_mw": dict(results.deficit),
                "bus_surplus_mw": dict(results.surplus),
                "objective_nzd": dict(results.objective_components),
            }
        )


def ac_network_formulation(*, preprocess: bool = False) -> Formulation:
    """Return the modular Gate 5 AC network and security profile."""

    return Formulation(
        formulation_id=AC_NETWORK_FORMULATION_ID,
        components=(
            CoreDomainsComponent,
            EnergyOffersComponent,
            DemandBidsComponent,
            EnergyScarcityComponent,
            NetworkDomainsComponent,
            ACNetworkComponent,
            GenerationRampingComponent,
            NetworkSecurityComponent,
            NetworkEconomicsComponent,
        ),
        preprocessors=(NetworkPreprocessor,) if preprocess else (),
        solve_policy=NetworkSolvePolicy,
        pricing_engine=NetworkPricingEngine,
        result_schema=NetworkResultSchema,
        report_renderer=NetworkReportRenderer,
    )
