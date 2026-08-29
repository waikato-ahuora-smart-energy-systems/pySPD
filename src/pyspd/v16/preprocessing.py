"""Pure, deterministic SPD v16 preprocessing deltas."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

type Key = tuple[str, ...]

BATTERY_MAPPING_OVERRIDES = frozenset(
    {
        ("BRB0331 RUK99", "BRB0331 RUK0"),
        ("HLY0331 RHO99", "HLY0331 RHO0"),
        ("GLN0332 GLB99", "GLN0332 GLB0"),
    }
)


def capped_offer_blocks(
    blocks: Sequence[Key],
    *,
    offer_mw: Mapping[Key, float],
    reserve_generation_maximum: Mapping[Key, float],
    potential_mw: Mapping[Key, float],
    generation_start: Mapping[Key, float],
    ramp_rate_up: Mapping[Key, float],
    interval_minutes: Mapping[Key, float],
    block_order: Mapping[str, int],
) -> dict[Key, float]:
    """Apply SPD v16 section 4.9.1.1 caps in source block order."""

    output: dict[Key, float] = {}
    offers = sorted({block[:3] for block in blocks})
    for offer in offers:
        period = offer[:2]
        maximum = min(
            reserve_generation_maximum.get(offer, 0.0),
            potential_mw.get(offer, 0.0),
            generation_start.get(offer, 0.0)
            + ramp_rate_up.get(offer, 0.0) * interval_minutes.get(period, 0.0) / 60.0,
        )
        cumulative = 0.0
        offer_blocks = sorted(
            (block for block in blocks if block[:3] == offer),
            key=lambda block: block_order[block[3]],
        )
        for block in offer_blocks:
            quantity = max(0.0, float(offer_mw.get(block, 0.0)))
            output[block] = min(quantity, max(0.0, maximum - cumulative))
            cumulative += quantity
    return output


def same_price_same_bus_pairs(
    blocks: Sequence[Key],
    *,
    offer_price: Mapping[Key, float],
    offer_bus: frozenset[Key],
    capped_mw: Mapping[Key, float],
    offer_order: Mapping[str, int],
) -> frozenset[Key]:
    """Create the ordered, positive-denominator v16 tie-break domain."""

    buses = {
        block[:3]: {key[3] for key in offer_bus if key[:3] == block[:3]}
        for block in blocks
    }
    pairs: set[Key] = set()
    for left in blocks:
        for right in blocks:
            if left[:2] != right[:2] or left[2] == right[2]:
                continue
            if offer_order[left[2]] >= offer_order[right[2]]:
                continue
            if offer_price[left] != offer_price[right]:
                continue
            if capped_mw.get(left, 0.0) <= 0.0 or capped_mw.get(right, 0.0) <= 0.0:
                continue
            if not buses[left[:3]] & buses[right[:3]]:
                continue
            pairs.add((*left, right[2], right[3]))
    return frozenset(pairs)


@dataclass(frozen=True, slots=True)
class BatteryPairInputs:
    load_like_nodes: frozenset[Key]
    generation_nodes: frozenset[Key]
    bid_node_trader: frozenset[Key]
    offer_node_trader: frozenset[Key]
    bus_unit_key3_match: frozenset[Key]
    mapping_overrides: frozenset[tuple[str, str]] = BATTERY_MAPPING_OVERRIDES


def derive_battery_pairs(inputs: BatteryPairInputs) -> frozenset[Key]:
    """Apply v16 pairing rules and the official multi-pair ambiguity safeguard."""

    candidates: set[Key] = set()
    for load in inputs.load_like_nodes:
        for generation in inputs.generation_nodes:
            if load[:2] != generation[:2]:
                continue
            common_trader = any(
                (*load, trader) in inputs.bid_node_trader
                and (*generation, trader) in inputs.offer_node_trader
                for trader in {
                    key[3]
                    for key in inputs.bid_node_trader | inputs.offer_node_trader
                    if key[:2] == load[:2]
                }
            )
            matched = (*load[:2], load[2], generation[2]) in inputs.bus_unit_key3_match
            overridden = (load[2], generation[2]) in inputs.mapping_overrides
            if common_trader and (matched or overridden):
                candidates.add((*load, generation[2]))
    counts = Counter(node for pair in candidates for node in pair[2:])
    ambiguous = {node for node, count in counts.items() if count > 1}
    return frozenset(
        pair
        for pair in candidates
        if pair[2] not in ambiguous and pair[3] not in ambiguous
    )
