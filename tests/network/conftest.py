from __future__ import annotations

from dataclasses import fields

from pyspd.core_energy import CoreEnergyCase
from pyspd.network import NetworkCase, NetworkData


def make_network_case(
    *,
    load: float = 50.0,
    offer_limit: float = 100.0,
    offer_price: float = 10.0,
    generation_bus: str = "B1",
    load_bus: str = "B2",
    capacity: float = 100.0,
    fixed_loss: float = 0.0,
    loss_segments: tuple[tuple[str, float, float], ...] = (("ls1", 100.0, 0.0),),
    connected: bool = True,
    branch_constraints: tuple[tuple[str, float, float, float], ...] = (),
    market_constraints: tuple[tuple[str, float, float, float], ...] = (),
) -> NetworkCase:
    period = ("C1", "T1")
    region = (*period, "NI")
    buses = frozenset({(*period, "B1"), (*period, "B2")})
    nodes = frozenset({(*period, "N1"), (*period, "N2")})
    offer = (*period, "GEN")
    block = (*offer, "1")
    core = CoreEnergyCase(
        case_id="C1",
        periods=frozenset({period}),
        regions=frozenset({region}),
        offers=frozenset({offer}),
        offer_blocks=frozenset({block}),
        primary_offers=frozenset({offer}),
        nodes=nodes,
        offer_region={offer: region},
        node_region={node: region for node in nodes},
        required_load={region: load},
        offer_limit={block: offer_limit},
        offer_price={block: offer_price},
        generation_start={offer: 0.0},
        ramp_rate_up={offer: 10_000.0},
        ramp_rate_down={offer: 10_000.0},
        interval_minutes={period: 30.0},
        study_mode={period: 130.0},
    )
    branch = (*period, "L1")
    branches = frozenset({branch}) if connected else frozenset()
    node_for_bus = {"B1": "N1", "B2": "N2"}
    offer_node = (*offer, node_for_bus[generation_bus])
    constraint_keys = frozenset((*period, row[0]) for row in branch_constraints)
    market_keys = frozenset((*period, row[0]) for row in market_constraints)
    network = NetworkData(
        buses=buses,
        branches=branches,
        ac_branches=branches,
        node_bus=frozenset(
            {(*period, "N1", "B1"), (*period, "N2", "B2")}
        ),
        bus_island=frozenset(
            {(*period, "B1", "NI"), (*period, "B2", "NI")}
        ),
        branch_from_bus=frozenset({(*branch, "B1")}) if connected else frozenset(),
        branch_to_bus=frozenset({(*branch, "B2")}) if connected else frozenset(),
        branch_bus_connect=(
            frozenset({(*branch, "B1"), (*branch, "B2")})
            if connected
            else frozenset()
        ),
        offer_node=frozenset({offer_node}),
        bid_node=frozenset(),
        reference_buses=(
            frozenset({(*period, "B1")})
            if connected
            else buses
        ),
        valid_ac_loss_segments=frozenset(
            (*branch, segment, direction)
            for segment, _width, _factor in loss_segments
            for direction in ("forward", "backward")
        )
        if connected
        else frozenset(),
        branch_constraints=constraint_keys,
        market_node_constraints=market_keys,
        positive_offers=frozenset({offer}),
        node_bus_allocation={
            (*period, "N1", "B1"): 1.0,
            (*period, "N2", "B2"): 1.0,
        },
        node_load={
            (*period, "N1"): load if load_bus == "B1" else 0.0,
            (*period, "N2"): load if load_bus == "B2" else 0.0,
        },
        bus_electrical_island={bus: 1.0 for bus in buses},
        branch_capacity={
            (*branch, direction): capacity
            for direction in ("forward", "backward")
        }
        if connected
        else {},
        branch_susceptance={branch: 100.0} if connected else {},
        branch_fixed_loss={branch: fixed_loss} if connected else {},
        ac_loss_segment_mw={
            (*branch, segment, direction): width
            for segment, width, _factor in loss_segments
            for direction in ("forward", "backward")
        }
        if connected
        else {},
        ac_loss_segment_factor={
            (*branch, segment, direction): factor
            for segment, _width, factor in loss_segments
            for direction in ("forward", "backward")
        }
        if connected
        else {},
        branch_constraint_sense={
            (*period, name): sense
            for name, sense, _limit, _factor in branch_constraints
        },
        branch_constraint_limit={
            (*period, name): limit
            for name, _sense, limit, _factor in branch_constraints
        },
        branch_constraint_factor={
            (*period, name, "L1"): factor
            for name, _sense, _limit, factor in branch_constraints
        }
        if connected
        else {},
        market_node_constraint_sense={
            (*period, name): sense
            for name, sense, _limit, _factor in market_constraints
        },
        market_node_constraint_limit={
            (*period, name): limit
            for name, _sense, limit, _factor in market_constraints
        },
        market_node_energy_offer_factor={
            (*period, name, "GEN"): factor
            for name, _sense, _limit, factor in market_constraints
        },
        market_node_energy_bid_factor={},
    )
    values = {
        item.name: getattr(core, item.name)
        for item in fields(CoreEnergyCase)
        if item.init
    }
    return NetworkCase(**values, network=network)
