from __future__ import annotations

from dataclasses import fields, replace

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
    bid_limit: float | None = None,
    bid_price: float = 100.0,
) -> NetworkCase:
    period = ("C1", "T1")
    region = (*period, "NI")
    buses = frozenset({(*period, "B1"), (*period, "B2")})
    nodes = frozenset({(*period, "N1"), (*period, "N2")})
    offer = (*period, "GEN")
    block = (*offer, "1")
    bid = (*period, "BID")
    bid_block = (*bid, "1")
    bids = frozenset({bid}) if bid_limit is not None else frozenset()
    bid_blocks = frozenset({bid_block}) if bid_limit is not None else frozenset()
    core = CoreEnergyCase(
        case_id="C1",
        periods=frozenset({period}),
        regions=frozenset({region}),
        offers=frozenset({offer}),
        offer_blocks=frozenset({block}),
        bids=bids,
        bid_blocks=bid_blocks,
        primary_offers=frozenset({offer}),
        nodes=nodes,
        offer_region={offer: region},
        bid_region={bid: region} if bid_limit is not None else {},
        node_region={node: region for node in nodes},
        required_load={region: load},
        offer_limit={block: offer_limit},
        offer_price={block: offer_price},
        bid_limit={bid_block: bid_limit} if bid_limit is not None else {},
        bid_price={bid_block: bid_price} if bid_limit is not None else {},
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
        bid_node=(
            frozenset({(*bid, node_for_bus[load_bus])})
            if bid_limit is not None
            else frozenset()
        ),
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
        market_node_energy_bid_factor=(
            {
                (*period, name, "BID"): factor
                for name, _sense, _limit, factor in market_constraints
            }
            if bid_limit is not None
            else {}
        ),
    )
    values = {
        item.name: getattr(core, item.name)
        for item in fields(CoreEnergyCase)
        if item.init
    }
    return NetworkCase(**values, network=network)


def make_three_bus_case() -> NetworkCase:
    base = make_network_case(load=0.0)
    assert base.network is not None
    period = ("C1", "T1")
    region = (*period, "NI")
    node3 = (*period, "N3")
    bus3 = (*period, "B3")
    branch1 = (*period, "L1")
    branch2 = (*period, "L2")
    branches = frozenset({branch1, branch2})
    loss_segments = frozenset(
        (*branch, "ls1", direction)
        for branch in branches
        for direction in ("forward", "backward")
    )
    network = replace(
        base.network,
        buses=base.network.buses | {bus3},
        branches=branches,
        ac_branches=branches,
        node_bus=base.network.node_bus | {(*period, "N3", "B3")},
        bus_island=base.network.bus_island | {(*period, "B3", "NI")},
        branch_from_bus=frozenset(
            {(*branch1, "B1"), (*branch2, "B2")}
        ),
        branch_to_bus=frozenset(
            {(*branch1, "B2"), (*branch2, "B3")}
        ),
        branch_bus_connect=frozenset(
            {
                (*branch1, "B1"),
                (*branch1, "B2"),
                (*branch2, "B2"),
                (*branch2, "B3"),
            }
        ),
        valid_ac_loss_segments=loss_segments,
        node_bus_allocation={
            **base.network.node_bus_allocation,
            (*period, "N3", "B3"): 1.0,
        },
        node_load={
            (*period, "N1"): 0.0,
            (*period, "N2"): 0.0,
            node3: 50.0,
        },
        bus_electrical_island={
            **base.network.bus_electrical_island,
            bus3: 1.0,
        },
        branch_capacity={
            (*branch, direction): 100.0
            for branch in branches
            for direction in ("forward", "backward")
        },
        branch_susceptance={branch: 100.0 for branch in branches},
        branch_fixed_loss={branch: 0.0 for branch in branches},
        ac_loss_segment_mw={key: 100.0 for key in loss_segments},
        ac_loss_segment_factor={key: 0.0 for key in loss_segments},
    )
    return replace(
        base,
        nodes=base.nodes | {node3},
        node_region={**base.node_region, node3: region},
        required_load={region: 50.0},
        network=network,
    )
