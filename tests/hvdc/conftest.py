from __future__ import annotations

from dataclasses import fields, replace

from pyspd.hvdc import HvdcCase, HvdcData, SosRepresentation
from pyspd.network import NetworkCase
from tests.network.conftest import make_network_case


def make_hvdc_case(
    *,
    load: float = 40.0,
    generation_bus: str = "B1",
    load_bus: str = "B2",
    breakpoint_flow: tuple[float, ...] = (0.0, 50.0, 100.0),
    breakpoint_loss: tuple[float, ...] = (0.0, 2.0, 8.0),
    capacity: float = 100.0,
    fixed_loss: float = 0.0,
    enforce: bool = False,
    native_sos: bool = False,
    opposing_links: bool = False,
    bid_limit: float | None = None,
) -> HvdcCase:
    base = make_network_case(
        load=load,
        generation_bus=generation_bus,
        load_bus=load_bus,
        connected=False,
        bid_limit=bid_limit,
    )
    assert base.network is not None
    period = ("C1", "T1")
    primary = (*period, "H1")
    links = {primary}
    endpoints = {primary: (generation_bus, load_bus)}
    if opposing_links:
        reverse = (*period, "H2")
        links.add(reverse)
        endpoints[reverse] = (load_bus, generation_bus)
    frozen_links = frozenset(links)
    network = replace(
        base.network,
        branches=frozen_links,
        ac_branches=frozenset(),
        branch_from_bus=frozenset(
            (*link, endpoints[link][0]) for link in frozen_links
        ),
        branch_to_bus=frozenset(
            (*link, endpoints[link][1]) for link in frozen_links
        ),
        branch_bus_connect=frozenset(
            (*link, bus) for link in frozen_links for bus in endpoints[link]
        ),
        valid_ac_loss_segments=frozenset(),
        branch_capacity={
            (*link, direction): capacity
            for link in frozen_links
            for direction in ("forward", "backward")
        },
        branch_susceptance={},
        branch_fixed_loss={link: fixed_loss for link in frozen_links},
        ac_loss_segment_mw={},
        ac_loss_segment_factor={},
    )
    segment_names = tuple(f"bp{index}" for index in range(1, len(breakpoint_flow) + 1))
    breakpoints = frozenset(
        (*link, segment) for link in frozen_links for segment in segment_names
    )
    discrete = base.bid_blocks if bid_limit is not None else frozenset()
    directions = {
        link: "forward" if endpoints[link] == ("B1", "B2") else "backward"
        for link in frozen_links
    }
    hvdc = HvdcData(
        links=frozen_links,
        sending_bus=frozenset(
            (*link, endpoints[link][0]) for link in frozen_links
        ),
        receiving_bus=frozenset(
            (*link, endpoints[link][1]) for link in frozen_links
        ),
        link_bus=frozenset(
            (*link, bus) for link in frozen_links for bus in endpoints[link]
        ),
        breakpoints=breakpoints,
        breakpoint_order={
            (*link, segment): float(index)
            for link in frozen_links
            for index, segment in enumerate(segment_names, start=1)
        },
        breakpoint_flow={
            (*link, segment): breakpoint_flow[index]
            for link in frozen_links
            for index, segment in enumerate(segment_names)
        },
        breakpoint_loss={
            (*link, segment): breakpoint_loss[index]
            for link in frozen_links
            for index, segment in enumerate(segment_names)
        },
        lambda_weight={key: 1.0 for key in breakpoints},
        capacity={link: capacity for link in frozen_links},
        discrete_bid_blocks=discrete,
        link_direction=directions,
        enforce_sos2=enforce,
        enforce_flow_direction=enforce,
        sos_representation=(
            SosRepresentation.NATIVE
            if native_sos
            else SosRepresentation.PORTABLE
        ),
        circulation_tolerance=1e-7,
        nonphysical_loss_tolerance=1e-7,
    )
    values = {
        item.name: getattr(base, item.name)
        for item in fields(NetworkCase)
        if item.init
    }
    values["network"] = network
    return HvdcCase(**values, hvdc=hvdc)
