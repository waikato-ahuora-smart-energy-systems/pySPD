"""Immutable normalized inputs for the Gate 5 AC-network formulation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from types import MappingProxyType

from pyspd.contracts import CaseData
from pyspd.core_energy.data import CoreEnergyCase
from pyspd.preprocess import PreprocessingResult
from pyspd.preprocess.input import CaseInput, nonzero

type Key = tuple[str, ...]

AC_NETWORK_FORMULATION_ID = "vspd-v5.0.6-ac-network"


class NetworkDataError(ValueError):
    """Normalized network data violates a model invariant."""


def _proxy[K, V](values: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class NetworkData:
    buses: frozenset[Key]
    branches: frozenset[Key]
    ac_branches: frozenset[Key]
    node_bus: frozenset[Key]
    bus_island: frozenset[Key]
    branch_from_bus: frozenset[Key]
    branch_to_bus: frozenset[Key]
    branch_bus_connect: frozenset[Key]
    offer_node: frozenset[Key]
    bid_node: frozenset[Key]
    reference_buses: frozenset[Key]
    valid_ac_loss_segments: frozenset[Key]
    branch_constraints: frozenset[Key]
    market_node_constraints: frozenset[Key]
    positive_offers: frozenset[Key]
    node_bus_allocation: Mapping[Key, float]
    node_load: Mapping[Key, float]
    bus_electrical_island: Mapping[Key, float]
    branch_capacity: Mapping[Key, float]
    branch_susceptance: Mapping[Key, float]
    branch_fixed_loss: Mapping[Key, float]
    ac_loss_segment_mw: Mapping[Key, float]
    ac_loss_segment_factor: Mapping[Key, float]
    branch_constraint_sense: Mapping[Key, float]
    branch_constraint_limit: Mapping[Key, float]
    branch_constraint_factor: Mapping[Key, float]
    market_node_constraint_sense: Mapping[Key, float]
    market_node_constraint_limit: Mapping[Key, float]
    market_node_energy_offer_factor: Mapping[Key, float]
    market_node_energy_bid_factor: Mapping[Key, float]
    receiving_end_loss_proportion: float = 1.0
    use_ac_branch_limits: bool = True
    bus_deficit_penalty: float = 500_000.0
    bus_surplus_penalty: float = 500_000.0
    branch_flow_surplus_penalty: float = 600_000.0
    branch_constraint_deficit_penalty: float = 650_000.0
    branch_constraint_surplus_penalty: float = 650_000.0
    market_node_deficit_penalty: float = 700_000.0
    market_node_surplus_penalty: float = 700_000.0

    def __post_init__(self) -> None:
        for name in (
            "buses",
            "branches",
            "ac_branches",
            "node_bus",
            "bus_island",
            "branch_from_bus",
            "branch_to_bus",
            "branch_bus_connect",
            "offer_node",
            "bid_node",
            "reference_buses",
            "valid_ac_loss_segments",
            "branch_constraints",
            "market_node_constraints",
            "positive_offers",
        ):
            object.__setattr__(self, name, frozenset(getattr(self, name)))
        for name in (
            "node_bus_allocation",
            "node_load",
            "bus_electrical_island",
            "branch_capacity",
            "branch_susceptance",
            "branch_fixed_loss",
            "ac_loss_segment_mw",
            "ac_loss_segment_factor",
            "branch_constraint_sense",
            "branch_constraint_limit",
            "branch_constraint_factor",
            "market_node_constraint_sense",
            "market_node_constraint_limit",
            "market_node_energy_offer_factor",
            "market_node_energy_bid_factor",
        ):
            object.__setattr__(self, name, _proxy(getattr(self, name)))
        self._validate()

    def _validate(self) -> None:
        if not self.buses:
            raise NetworkDataError("at least one bus is required")
        if not self.ac_branches <= self.branches:
            raise NetworkDataError("AC branch lies outside the branch domain")
        if not self.reference_buses <= self.buses:
            raise NetworkDataError("reference bus lies outside the bus domain")
        if {key[:3] for key in self.valid_ac_loss_segments} - self.ac_branches:
            raise NetworkDataError("AC loss segment has no active AC branch")
        if set(self.node_load) != {key[:3] for key in self.node_bus}:
            raise NetworkDataError("node loads do not cover the connected-node domain")
        if set(self.branch_susceptance) != set(self.ac_branches):
            raise NetworkDataError("susceptance does not cover active AC branches")
        if set(self.branch_fixed_loss) != set(self.branches):
            raise NetworkDataError("fixed losses do not cover active branches")
        expected_capacity = {
            (*branch, direction)
            for branch in self.branches
            for direction in ("forward", "backward")
        }
        if set(self.branch_capacity) != expected_capacity:
            raise NetworkDataError("directional capacity does not cover active branches")
        if set(self.branch_constraint_sense) != set(self.branch_constraints):
            raise NetworkDataError("branch constraint sense does not cover its domain")
        if set(self.branch_constraint_limit) != set(self.branch_constraints):
            raise NetworkDataError("branch constraint limit does not cover its domain")
        if set(self.market_node_constraint_sense) != set(
            self.market_node_constraints
        ):
            raise NetworkDataError("market-node sense does not cover its domain")
        if set(self.market_node_constraint_limit) != set(
            self.market_node_constraints
        ):
            raise NetworkDataError("market-node limit does not cover its domain")
        mappings = (
            self.node_bus_allocation,
            self.node_load,
            self.bus_electrical_island,
            self.branch_capacity,
            self.branch_susceptance,
            self.branch_fixed_loss,
            self.ac_loss_segment_mw,
            self.ac_loss_segment_factor,
            self.branch_constraint_sense,
            self.branch_constraint_limit,
            self.branch_constraint_factor,
            self.market_node_constraint_sense,
            self.market_node_constraint_limit,
            self.market_node_energy_offer_factor,
            self.market_node_energy_bid_factor,
        )
        if any(
            not math.isfinite(float(value))
            for mapping in mappings
            for value in mapping.values()
        ):
            raise NetworkDataError("all network inputs must be finite")
        if not 0.0 <= self.receiving_end_loss_proportion <= 1.0:
            raise NetworkDataError("loss allocation proportion must lie in [0, 1]")

    def with_node_load(self, node: Key, value: float) -> NetworkData:
        if node not in self.node_load:
            raise NetworkDataError(f"unknown node: {node}")
        loads = dict(self.node_load)
        loads[node] = float(value)
        return replace(self, node_load=loads)

    @classmethod
    def from_sources(
        cls, result: PreprocessingResult, case_data: CaseData
    ) -> NetworkData:
        source = CaseInput(case_data)
        branches = result.set("branch").members
        ac_branches = result.set("ac_branch").members
        buses = result.set("bus").members
        nodes = result.set("node").members
        offers = result.set("offer").members
        bids = result.set("bid").members
        node_bus = result.set("node_bus").members
        offer_node = frozenset(
            key
            for key in source.members("i_dateTimeOfferNode")
            if key[:3] in offers and key[:2] + (key[3],) in nodes
        )
        bid_node = frozenset(
            key
            for key in source.members("i_dateTimeBidNode")
            if key[:3] in bids and key[:2] + (key[3],) in nodes
        )
        reference_nodes = source.component(
            "i_dateTimeNodeParameter", "referenceNode"
        )
        reference_buses = frozenset(
            (case, datetime, bus)
            for case, datetime, node, bus in node_bus
            if nonzero(reference_nodes.get((case, datetime, node), 0.0))
        )
        branch_constraints = result.set("branch_constraint").members
        market_constraints = result.set("market_node_constraint").members
        branch_factors = {
            key: value
            for key, value in source.numeric(
                "i_dateTimeBranchConstraintFactors"
            ).items()
            if key[:3] in branch_constraints and key[:2] + (key[3],) in branches
        }
        offer_factors = {
            key: value
            for key, value in source.numeric("i_dateTimeMNCnstrEnrgFactors").items()
            if key[:3] in market_constraints and key[:2] + (key[3],) in offers
        }
        bid_factors = {
            key: value
            for key, value in source.numeric(
                "i_dateTimeMNCnstrEnrgBidFactors"
            ).items()
            if key[:3] in market_constraints and key[:2] + (key[3],) in bids
        }
        return cls(
            buses=buses,
            branches=branches,
            ac_branches=ac_branches,
            node_bus=node_bus,
            bus_island=result.set("bus_island").members,
            branch_from_bus=result.set("branch_from_bus").members,
            branch_to_bus=result.set("branch_to_bus").members,
            branch_bus_connect=result.set("branch_bus_connect").members,
            offer_node=offer_node,
            bid_node=bid_node,
            reference_buses=reference_buses,
            valid_ac_loss_segments=frozenset(
                key
                for key in result.set("valid_loss_segment").members
                if key[:3] in ac_branches
            ),
            branch_constraints=branch_constraints,
            market_node_constraints=market_constraints,
            positive_offers=result.set("positive_energy_offer").members,
            node_bus_allocation={
                key: value
                for key, value in source.numeric(
                    "i_dateTimeNodeBusAllocationFactor"
                ).items()
                if key in node_bus
            },
            node_load={key: result.parameter("required_load").get(key) for key in nodes},
            bus_electrical_island={
                key: source.numeric("i_dateTimeBusElectricalIsland").get(key, 0.0)
                for key in buses
            },
            branch_capacity=result.parameter("branch_capacity").values,
            branch_susceptance=result.parameter("branch_susceptance").values,
            branch_fixed_loss=result.parameter("branch_fixed_loss").values,
            ac_loss_segment_mw=result.parameter("ac_branch_loss_mw").values,
            ac_loss_segment_factor=result.parameter(
                "ac_branch_loss_factor"
            ).values,
            branch_constraint_sense={
                key: result.parameter("branch_constraint_sense").get(key)
                for key in branch_constraints
            },
            branch_constraint_limit={
                key: result.parameter("branch_constraint_limit").get(key)
                for key in branch_constraints
            },
            branch_constraint_factor=branch_factors,
            market_node_constraint_sense={
                key: result.parameter("market_node_constraint_sense").get(key)
                for key in market_constraints
            },
            market_node_constraint_limit={
                key: result.parameter("market_node_constraint_limit").get(key)
                for key in market_constraints
            },
            market_node_energy_offer_factor=offer_factors,
            market_node_energy_bid_factor=bid_factors,
        )


@dataclass(frozen=True, slots=True)
class NetworkCase(CoreEnergyCase):
    network: NetworkData | None = None
    formulation_id: str = field(
        default=AC_NETWORK_FORMULATION_ID, init=False, repr=False
    )

    def __post_init__(self) -> None:
        super(NetworkCase, self).__post_init__()
        if self.network is None:
            raise NetworkDataError("NetworkCase requires NetworkData")
        if {key[:2] for key in self.network.buses} - self.periods:
            raise NetworkDataError("network bus lies outside the period domain")

    @classmethod
    def from_sources(
        cls, result: PreprocessingResult, case_data: CaseData
    ) -> NetworkCase:
        core = CoreEnergyCase.from_preprocessing(result)
        values = {
            item.name: getattr(core, item.name)
            for item in fields(CoreEnergyCase)
            if item.init
        }
        return cls(
            **values,
            network=NetworkData.from_sources(result, case_data),
        )
