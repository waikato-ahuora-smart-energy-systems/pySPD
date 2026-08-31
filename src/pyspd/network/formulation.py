"""Public Gate 5 class-based AC-network formulation profile."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
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
    convention: str = "negative objective sensitivity to +1 MW nodal load"

    def __post_init__(self) -> None:
        object.__setattr__(self, "bus", MappingProxyType(dict(self.bus)))
        object.__setattr__(self, "node", MappingProxyType(dict(self.node)))
        object.__setattr__(
            self, "raw_bus_duals", MappingProxyType(dict(self.raw_bus_duals))
        )
        object.__setattr__(self, "dead_nodes", frozenset(self.dead_nodes))


class NetworkPricingEngine(PricingEngine):
    supported_formulations = _SUPPORTED

    @staticmethod
    def _canonical_zero_flow_leaf_prices(
        built_model: BuiltModel,
        case: NetworkCase,
        prices: dict[Key, float],
        *,
        tolerance: float = 1e-9,
    ) -> None:
        """Select vSPD's +load derivative at a zero-flow loss kink.

        A zero-injection leaf on a lossy branch has two valid LP duals: the
        derivative for an incremental export and the derivative for an
        incremental load.  GAMS/HiGHS reports the latter.  HighsPy can select
        the former from the same optimal face, so normalize that otherwise
        solver-order-dependent dual to the exact one-sided load sensitivity.
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
        receiving_share = network.receiving_end_loss_proportion
        for leaf, branches in sorted(incident.items()):
            if len(branches) != 1:
                continue
            if network.bus_electrical_island.get(leaf, 0.0) == 0.0:
                continue
            leaf_nodes = {
                (*leaf[:2], key[2])
                for key in network.node_bus
                if (*key[:2], key[3]) == leaf
            }
            if any(
                abs(network.node_load.get(node, 0.0)) > tolerance
                for node in leaf_nodes
            ) or any(
                (*key[:2], key[3]) in leaf_nodes
                for key in (*network.offer_node, *network.bid_node)
            ):
                continue
            branch = branches[0]
            if abs(float(pyo.value(branch_flow[branch]))) > tolerance:
                continue
            if any(
                abs(float(pyo.value(directed_flow[*branch, direction])))
                > tolerance
                for direction in ("forward", "backward")
            ):
                continue

            from_bus = next(
                key[3] for key in network.branch_from_bus if key[:3] == branch
            )
            to_bus = next(
                key[3] for key in network.branch_to_bus if key[:3] == branch
            )
            if leaf[2] == to_bus:
                parent = (*branch[:2], from_bus)
                inward_direction = "forward"
            elif leaf[2] == from_bus:
                parent = (*branch[:2], to_bus)
                inward_direction = "backward"
            else:  # pragma: no cover - guarded by the network-data contract
                continue
            factors = [
                factor
                for key, factor in network.ac_loss_segment_factor.items()
                if key[:3] == branch and key[4] == inward_direction
            ]
            if not factors:
                continue
            first_factor = min(factors)
            if first_factor <= 0.0:
                continue
            denominator = 1.0 - receiving_share * first_factor
            if denominator <= 0.0:
                raise ValueError("AC loss factor makes incremental delivery invalid")
            prices[leaf] = prices[parent] * (
                1.0 + (1.0 - receiving_share) * first_factor
            ) / denominator

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
        self._canonical_zero_flow_leaf_prices(built_model, case, raw)
        # In ACnodeNetInjectionDefinition2, required load appears with a
        # negative coefficient on the right-hand side.  The equality marginal
        # therefore already has the positive market-price sign used by vSPD.
        bus_prices = dict(raw)
        node_prices: dict[Key, float] = {}
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
        return NetworkPrices(bus_prices, node_prices, raw, frozenset(dead))


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
