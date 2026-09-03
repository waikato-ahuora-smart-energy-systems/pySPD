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
        recursion; unanchored zero-loss cycles retain their solver duals.
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
        generation = built_model.artifacts["generation"]
        purchase = built_model.artifacts["purchase"]
        scarcity = built_model.artifacts["energy_scarcity_node"]
        receiving_share = network.receiving_end_loss_proportion
        original = dict(prices)

        def first_factor(branch: Key, direction: str) -> float:
            factors = [
                factor
                for key, factor in network.ac_loss_segment_factor.items()
                if key[:3] == branch and key[4] == direction
            ]
            return min(factors, default=0.0)

        def passive(bus: Key, branches: tuple[Key, ...]) -> bool:
            if network.bus_electrical_island.get(bus, 0.0) == 0.0:
                return False
            if any(
                abs(float(pyo.value(branch_flow[branch]))) > tolerance
                or abs(network.branch_fixed_loss.get(branch, 0.0)) > tolerance
                or any(
                    abs(float(pyo.value(directed_flow[*branch, direction])))
                    > tolerance
                    for direction in ("forward", "backward")
                )
                for branch in branches
            ):
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
                if tuple(prefix) == bus[:2] and node in nodes
            ):
                return False
            return not any(
                abs(float(pyo.value(purchase[(*prefix, bid)]))) > tolerance
                for *prefix, bid, node in network.bid_node
                if tuple(prefix) == bus[:2] and node in nodes
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

        def select(bus: Key, branch: Key, parent: Key) -> None:
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
                return
            selected[bus] = (
                branch,
                parent,
                first_factor(branch, inward_direction),
                first_factor(branch, outward_direction),
            )

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
                else None
            )
            if inward_factor == 0.0 and outward_factor == 0.0:
                value = parent_interval
                interval_memo[bus] = value
                return value
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
            parent_price = cplex_price(parent, visiting | {bus})
            parent_bounds = parent_interval or (parent_price, parent_price)
            export_ratio = (
                1.0 - receiving_share * outward_factor
            ) / outward_denominator
            load_ratio = (
                1.0 + (1.0 - receiving_share) * inward_factor
            ) / inward_denominator
            endpoints = tuple(
                bound * ratio
                for bound in parent_bounds
                for ratio in (export_ratio, load_ratio)
            )
            value = (min(endpoints), max(endpoints))
            interval_memo[bus] = value
            return value

        for bus in selected:
            prices[bus] = cplex_price(bus, frozenset())
            analytic_interval(bus, frozenset())
        return {
            bus: interval
            for bus, interval in interval_memo.items()
            if interval is not None and interval[1] - interval[0] > tolerance
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
