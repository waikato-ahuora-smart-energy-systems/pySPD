from __future__ import annotations

from pyspd.v16.preprocessing import (
    BatteryPairInputs,
    capped_offer_blocks,
    derive_battery_pairs,
    same_price_same_bus_pairs,
)


def test_capped_offer_blocks_apply_cap_in_source_block_order() -> None:
    blocks = (("C", "T", "O", "t1"), ("C", "T", "O", "t2"))
    result = capped_offer_blocks(
        blocks,
        offer_mw={blocks[0]: 30.0, blocks[1]: 40.0},
        reserve_generation_maximum={("C", "T", "O"): 60.0},
        potential_mw={("C", "T", "O"): 55.0},
        generation_start={("C", "T", "O"): 10.0},
        ramp_rate_up={("C", "T", "O"): 80.0},
        interval_minutes={("C", "T"): 30.0},
        block_order={"t1": 1, "t2": 2},
    )

    assert result == {blocks[0]: 30.0, blocks[1]: 20.0}


def test_tie_pairs_require_distinct_offers_equal_price_and_a_shared_bus() -> None:
    left = ("C", "T", "O1", "t1")
    right = ("C", "T", "O2", "t1")
    other = ("C", "T", "O3", "t1")
    pairs = same_price_same_bus_pairs(
        (left, right, other),
        offer_price={left: 10.0, right: 10.0, other: 11.0},
        offer_bus={
            ("C", "T", "O1", "B1"),
            ("C", "T", "O2", "B1"),
            ("C", "T", "O3", "B1"),
        },
        capped_mw={left: 20.0, right: 30.0, other: 40.0},
        offer_order={"O1": 1, "O2": 2, "O3": 3},
    )

    assert pairs == frozenset({("C", "T", "O1", "t1", "O2", "t1")})


def test_battery_pair_safeguard_removes_ambiguous_nodes() -> None:
    inputs = BatteryPairInputs(
        load_like_nodes=frozenset({("C", "T", "LOAD")}),
        generation_nodes=frozenset({("C", "T", "GEN1"), ("C", "T", "GEN2")}),
        bid_node_trader=frozenset({("C", "T", "LOAD", "TRADER")}),
        offer_node_trader=frozenset(
            {
                ("C", "T", "GEN1", "TRADER"),
                ("C", "T", "GEN2", "TRADER"),
            }
        ),
        bus_unit_key3_match=frozenset(
            {
                ("C", "T", "LOAD", "GEN1"),
                ("C", "T", "LOAD", "GEN2"),
            }
        ),
    )

    assert derive_battery_pairs(inputs) == frozenset()
