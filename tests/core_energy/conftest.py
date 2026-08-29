from __future__ import annotations

from collections.abc import Iterable

from pyspd.core_energy import CoreEnergyCase


def make_core_case(
    *,
    load: float = 0.0,
    offers: Iterable[tuple[str, float, float]] = (),
    bids: Iterable[tuple[str, float, float]] = (),
    starts: dict[str, float] | None = None,
    ramp_up: dict[str, float] | None = None,
    ramp_down: dict[str, float] | None = None,
    generation_maximum: dict[str, float] | None = None,
    interval_minutes: float = 30.0,
    study_mode: float = 130.0,
) -> CoreEnergyCase:
    period = ("C1", "T1")
    region = (*period, "NI")
    offer_rows = tuple(offers)
    bid_rows = tuple(bids)
    offer_keys = frozenset((*period, name) for name, _limit, _price in offer_rows)
    offer_blocks = frozenset(
        (*period, name, "1") for name, _limit, _price in offer_rows
    )
    bid_keys = frozenset((*period, name) for name, _limit, _price in bid_rows)
    bid_blocks = frozenset((*period, name, "1") for name, _limit, _price in bid_rows)
    starts = starts or {}
    ramp_up = ramp_up or {}
    ramp_down = ramp_down or {}
    generation_maximum = generation_maximum or {}
    return CoreEnergyCase(
        case_id="C1",
        periods=frozenset({period}),
        regions=frozenset({region}),
        offers=offer_keys,
        offer_blocks=offer_blocks,
        bids=bid_keys,
        bid_blocks=bid_blocks,
        primary_offers=offer_keys,
        offer_region={key: region for key in offer_keys},
        bid_region={key: region for key in bid_keys},
        required_load={region: load},
        offer_limit={
            (*period, name, "1"): limit for name, limit, _price in offer_rows
        },
        offer_price={
            (*period, name, "1"): price for name, _limit, price in offer_rows
        },
        bid_limit={
            (*period, name, "1"): limit for name, limit, _price in bid_rows
        },
        bid_price={
            (*period, name, "1"): price for name, _limit, price in bid_rows
        },
        generation_start={key: starts.get(key[2], 0.0) for key in offer_keys},
        ramp_rate_up={key: ramp_up.get(key[2], 10_000.0) for key in offer_keys},
        ramp_rate_down={key: ramp_down.get(key[2], 10_000.0) for key in offer_keys},
        interval_minutes={period: interval_minutes},
        study_mode={period: study_mode},
        generation_maximum={
            (*period, name): limit for name, limit in generation_maximum.items()
        },
    )
