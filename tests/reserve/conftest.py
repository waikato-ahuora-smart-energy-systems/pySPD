from __future__ import annotations

from dataclasses import fields, replace

from pyspd.hvdc import HvdcCase
from pyspd.reserve import ReserveCase, ReserveData
from pyspd.reserve.data import (
    BLOCKS,
    ENERGY_BREAKPOINTS,
    RESERVE_BREAKPOINTS,
    RESERVE_CLASSES,
    RESERVE_TYPES,
    RISK_CLASSES,
)
from tests.hvdc.conftest import make_hvdc_case


def make_reserve_case(*, secondary: bool = False) -> ReserveCase:
    base = make_hvdc_case(load=40.0, capacity=100.0)
    assert base.network is not None
    network = replace(
        base.network,
        bus_island=frozenset(
            {
                ("C1", "T1", "B1", "NI"),
                ("C1", "T1", "B2", "SI"),
            }
        ),
    )
    base = replace(base, network=network)
    islands = frozenset({("C1", "T1", "NI"), ("C1", "T1", "SI")})
    offer = ("C1", "T1", "GEN")
    generator = (*offer[:2], "NI", offer[2])
    risk_keys = {
        (*island, reserve_class, risk)
        for island in islands
        for reserve_class in RESERVE_CLASSES
        for risk in RISK_CLASSES
    }
    reserve_blocks = {
        (*offer, block, reserve_class, reserve_type)
        for block in BLOCKS
        for reserve_class in RESERVE_CLASSES
        for reserve_type in RESERVE_TYPES
    }
    energy_flow_values = (0.0, 15.0, 30.0, 50.0, 70.0, 85.0, 100.0)
    reserve_flow_values = tuple(float(value) for value in range(-60, 61, 10))
    reserve = ReserveData(
        islands=islands,
        offer_island=frozenset({(*offer, "NI")}),
        risk_generators=frozenset({generator}),
        primary_secondary_offer=frozenset(),
        risk_group_offer=frozenset({("C1", "T1", "G1", "GEN", "genRisk")}),
        island_risk_group=frozenset({("C1", "T1", "NI", "G1", "genRisk")}),
        island_link_risk_group=frozenset(),
        directional_risk_factor={},
        reserve_block_limit={
            key: 100.0 if key[3] == "t1" else 0.0 for key in reserve_blocks
        },
        reserve_block_price={
            key: {"PLRO": 1.0, "TWRO": 2.0, "ILRO": 3.0}[key[-1]]
            for key in reserve_blocks
        },
        reserve_offer_percent={
            (*offer, block, reserve_class): 1.0
            for block in BLOCKS
            for reserve_class in RESERVE_CLASSES
        },
        reserve_generation_maximum={offer: 100.0},
        reserve_maximum_factor={
            (*offer, reserve_class): 1.0 for reserve_class in RESERVE_CLASSES
        },
        risk_adjustment_factor={key: 1.0 for key in risk_keys},
        risk_minimum={key: 20.0 for key in risk_keys},
        free_reserve={key: 0.0 for key in risk_keys},
        hvdc_pole_ramp_up={key: 0.0 for key in risk_keys},
        secondary_risk_offer={
            (*offer, risk): 0.0 for risk in ("genRisk", "genRiskECE")
        },
        secondary_risk_group={
            ("C1", "T1", "G1", risk): 0.0
            for risk in ("genRisk", "genRiskECE")
        },
        fk_band={offer: 0.0},
        hvdc_secondary_enabled={
            (*island, risk): float(secondary)
            for island in islands
            for risk in ("HVDCsecRisk", "HVDCsecRiskECE")
        },
        hvdc_secondary_subtractor={island: 0.0 for island in islands},
        reserve_share_enabled={
            ("C1", "T1", reserve_class): 1.0
            for reserve_class in RESERVE_CLASSES
        },
        reserve_round_power={
            ("C1", "T1", reserve_class): 0.0
            for reserve_class in RESERVE_CLASSES
        },
        modulation_risk_class={
            ("C1", "T1", risk): 0.0 for risk in RISK_CLASSES
        },
        modulation_risk={("C1", "T1"): 0.0},
        round_power_zone_exit={
            ("C1", "T1", reserve_class): 0.0
            for reserve_class in RESERVE_CLASSES
        },
        monopole_minimum={("C1", "T1"): 0.0},
        hvdc_control_band={
            ("C1", "T1", direction): 100.0
            for direction in ("forward", "backward")
        },
        hvdc_maximum={island: 100.0 for island in islands},
        shared_nfr_maximum={island: 0.0 for island in islands},
        effective_factor={key: 1.0 for key in risk_keys},
        energy_breakpoint_flow={
            (*island, bp): energy_flow_values[index]
            for island in islands
            for index, bp in enumerate(ENERGY_BREAKPOINTS)
        },
        energy_breakpoint_loss={
            (*island, bp): 0.0 for island in islands for bp in ENERGY_BREAKPOINTS
        },
        reserve_breakpoint_flow={
            (*island, bp): reserve_flow_values[index]
            for island in islands
            for index, bp in enumerate(RESERVE_BREAKPOINTS)
        },
        reserve_breakpoint_loss={
            (*island, bp): 0.0 for island in islands for bp in RESERVE_BREAKPOINTS
        },
        reserve_scarcity_limit={
            (*island, reserve_class, block): 100.0
            for island in islands
            for reserve_class in RESERVE_CLASSES
            for block in BLOCKS
        },
        reserve_scarcity_price={
            (*island, reserve_class, block): 1_000.0 if block == "t1" else 0.0
            for island in islands
            for reserve_class in RESERVE_CLASSES
            for block in BLOCKS
        },
        reserve_scarcity_enabled={
            (*island, reserve_class): 1.0
            for island in islands
            for reserve_class in RESERVE_CLASSES
        },
        market_reserve_offer_factor={},
        market_reserve_bid_factor={},
    )
    values = {
        item.name: getattr(base, item.name)
        for item in fields(HvdcCase)
        if item.init
    }
    return ReserveCase(**values, reserve=reserve)
