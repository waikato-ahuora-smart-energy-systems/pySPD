"""Immutable normalized inputs for the Gate 4 core-energy formulation."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from pyspd.preprocess import PreprocessingResult

type Key = tuple[str, ...]
type Period = Key
type Region = Key
type Offer = Key
type OfferBlock = Key
type Bid = Key
type BidBlock = Key
type PrimarySecondary = Key

CORE_ENERGY_FORMULATION_ID = "vspd-v5.0.6-core-energy"


class CoreEnergyDataError(ValueError):
    """Normalized core-energy data violates a model invariant."""


def _proxy[K, V](values: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class CoreEnergyCase:
    """Solver-ready, immutable projection of Gate 3 preprocessing artifacts."""

    case_id: str
    periods: frozenset[Period]
    regions: frozenset[Region]
    offers: frozenset[Offer]
    offer_blocks: frozenset[OfferBlock]
    bids: frozenset[Bid] = frozenset()
    bid_blocks: frozenset[BidBlock] = frozenset()
    primary_offers: frozenset[Offer] = frozenset()
    primary_secondary: frozenset[PrimarySecondary] = frozenset()
    offer_region: Mapping[Offer, Region] = field(default_factory=dict)
    bid_region: Mapping[Bid, Region] = field(default_factory=dict)
    required_load: Mapping[Region, float] = field(default_factory=dict)
    offer_limit: Mapping[OfferBlock, float] = field(default_factory=dict)
    offer_price: Mapping[OfferBlock, float] = field(default_factory=dict)
    bid_limit: Mapping[BidBlock, float] = field(default_factory=dict)
    bid_price: Mapping[BidBlock, float] = field(default_factory=dict)
    generation_start: Mapping[Offer, float] = field(default_factory=dict)
    ramp_rate_up: Mapping[Offer, float] = field(default_factory=dict)
    ramp_rate_down: Mapping[Offer, float] = field(default_factory=dict)
    interval_minutes: Mapping[Period, float] = field(default_factory=dict)
    study_mode: Mapping[Period, float] = field(default_factory=dict)
    generation_maximum: Mapping[Offer, float] = field(default_factory=dict)
    preprocessing_signature: str | None = None
    balance_deficit_penalty: float = 500_000.0
    balance_surplus_penalty: float = 500_000.0
    ramp_deficit_penalty: float = 850_000.0
    ramp_surplus_penalty: float = 850_000.0
    movement_penalty: float = 0.0005

    formulation_id: str = field(
        default=CORE_ENERGY_FORMULATION_ID, init=False, repr=False
    )

    def __post_init__(self) -> None:
        set_fields = (
            "periods",
            "regions",
            "offers",
            "offer_blocks",
            "bids",
            "bid_blocks",
            "primary_offers",
            "primary_secondary",
        )
        for name in set_fields:
            object.__setattr__(self, name, frozenset(getattr(self, name)))
        map_fields = (
            "offer_region",
            "bid_region",
            "required_load",
            "offer_limit",
            "offer_price",
            "bid_limit",
            "bid_price",
            "generation_start",
            "ramp_rate_up",
            "ramp_rate_down",
            "interval_minutes",
            "study_mode",
            "generation_maximum",
        )
        for name in map_fields:
            object.__setattr__(self, name, _proxy(getattr(self, name)))
        self._validate()

    def _validate(self) -> None:
        if not self.case_id.strip() or not self.periods or not self.regions:
            raise CoreEnergyDataError("case_id, periods, and regions are required")
        if {region[:2] for region in self.regions} != self.periods:
            raise CoreEnergyDataError("every period must have exactly its declared regions")
        if set(self.offer_region) != set(self.offers):
            raise CoreEnergyDataError("every offer must map to exactly one region")
        if set(self.bid_region) != set(self.bids):
            raise CoreEnergyDataError("every bid must map to exactly one region")
        if not set(self.offer_region.values()) <= set(self.regions):
            raise CoreEnergyDataError("offer maps outside the region domain")
        if not set(self.bid_region.values()) <= set(self.regions):
            raise CoreEnergyDataError("bid maps outside the region domain")
        if {key[:3] for key in self.offer_blocks} - set(self.offers):
            raise CoreEnergyDataError("offer block has no parent offer")
        if {key[:3] for key in self.bid_blocks} - set(self.bids):
            raise CoreEnergyDataError("bid block has no parent bid")
        if not self.primary_offers <= self.offers:
            raise CoreEnergyDataError("primary offer is outside the offer domain")
        for case, period, primary, secondary in self.primary_secondary:
            if (case, period, primary) not in self.offers or (
                case,
                period,
                secondary,
            ) not in self.offers:
                raise CoreEnergyDataError("primary-secondary mapping is not closed")
        required_maps: dict[
            str, tuple[Mapping[Key, float], frozenset[Key]]
        ] = {
            "required_load": (self.required_load, self.regions),
            "offer_limit": (self.offer_limit, self.offer_blocks),
            "offer_price": (self.offer_price, self.offer_blocks),
            "bid_limit": (self.bid_limit, self.bid_blocks),
            "bid_price": (self.bid_price, self.bid_blocks),
            "generation_start": (self.generation_start, self.offers),
            "ramp_rate_up": (self.ramp_rate_up, self.offers),
            "ramp_rate_down": (self.ramp_rate_down, self.offers),
            "interval_minutes": (self.interval_minutes, self.periods),
            "study_mode": (self.study_mode, self.periods),
        }
        for name, (mapping, domain) in required_maps.items():
            if set(mapping) != set(domain):
                raise CoreEnergyDataError(f"{name} does not cover its domain")
        numeric_maps: list[Mapping[Key, float]] = [
            mapping for mapping, _domain in required_maps.values()
        ]
        numeric_maps.append(self.generation_maximum)
        if any(not math.isfinite(float(value)) for mapping in numeric_maps for value in mapping.values()):
            raise CoreEnergyDataError("all numeric inputs must be finite")
        if any(value < 0 for value in self.offer_limit.values()):
            raise CoreEnergyDataError("generation offer block limits must be nonnegative")
        if any(value <= 0 for value in self.interval_minutes.values()):
            raise CoreEnergyDataError("interval duration must be positive")
        if any(value < 0 for value in self.generation_maximum.values()):
            raise CoreEnergyDataError("generation maximum must be nonnegative")
        if not set(self.generation_maximum) <= set(self.offers):
            raise CoreEnergyDataError("generation maximum has no parent offer")

    def with_required_load(self, region: Region, value: float) -> CoreEnergyCase:
        if region not in self.regions:
            raise CoreEnergyDataError(f"unknown region: {region}")
        values = dict(self.required_load)
        values[region] = float(value)
        return replace(self, required_load=values)

    @classmethod
    def from_preprocessing(cls, result: PreprocessingResult) -> CoreEnergyCase:
        """Aggregate Gate 3 node data to independent per-island LP regions."""

        node_island = result.set("node_island").members
        regions = frozenset(key[:2] + (key[3],) for key in node_island)
        required_load: dict[Region, float] = defaultdict(float)
        node_load = result.parameter("required_load")
        for case, datetime, node, island in node_island:
            required_load[(case, datetime, island)] += node_load.get(
                (case, datetime, node)
            )

        offers = result.set("offer").members
        offer_region = _unique_region_map(
            offers, result.set("offer_island").members, "offer"
        )
        bids = result.set("bid").members
        bid_region = _unique_region_map(bids, result.set("bid_island").members, "bid")

        generation_maximum: dict[Offer, float] = {}
        intermittent = result.set("intermittent_offer").members
        responsive = result.set("price_responsive_offer").members
        potential = result.parameter("potential_mw")
        reserve_max = result.parameter("reserve_generation_maximum")
        for offer in intermittent & responsive:
            generation_maximum[offer] = min(
                potential.get(offer), reserve_max.get(offer)
            )

        periods = result.set("case_datetime").members
        return cls(
            case_id=result.case_id,
            periods=periods,
            regions=regions,
            offers=offers,
            offer_blocks=result.set("generation_offer_block").members,
            bids=bids,
            bid_blocks=result.set("demand_bid_block").members,
            primary_offers=result.set("primary_offer").members,
            primary_secondary=result.set("primary_secondary_offer").members,
            offer_region=offer_region,
            bid_region=bid_region,
            required_load=required_load,
            offer_limit=result.parameter("energy_offer_mw").values,
            offer_price=result.parameter("energy_offer_price").values,
            bid_limit=result.parameter("demand_bid_mw").values,
            bid_price=result.parameter("demand_bid_price").values,
            generation_start=result.parameter("generation_start").values,
            ramp_rate_up=result.parameter("ramp_rate_up").values,
            ramp_rate_down=result.parameter("ramp_rate_down").values,
            interval_minutes=result.parameter("interval_duration").values,
            study_mode=result.parameter("study_mode").values,
            generation_maximum=generation_maximum,
            preprocessing_signature=result.structural_signature,
        )


def _unique_region_map(
    domain: frozenset[tuple[str, ...]],
    mappings: frozenset[tuple[str, ...]],
    label: str,
) -> dict[tuple[str, ...], Region]:
    output: dict[tuple[str, ...], Region] = {}
    for item in domain:
        matches = [mapping for mapping in mappings if mapping[:3] == item]
        if len(matches) != 1:
            raise CoreEnergyDataError(
                f"{label} {item!r} must map to one region, got {len(matches)}"
            )
        output[item] = matches[0][:2] + (matches[0][3],)
    return output
