"""Immutable normalized data for the separately selected SPD v16 model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from datetime import date
from types import MappingProxyType

from pyspd.contracts import CaseData
from pyspd.preprocess import PreprocessingResult
from pyspd.preprocess.input import CaseInput
from pyspd.reserve.data import RESERVE_CLASSES, ReserveCase
from pyspd.v16.compatibility import (
    SPD16_FORMULATION_ID,
    Spd16CompatibilityPolicy,
)
from pyspd.v16.preprocessing import (
    BatteryPairInputs,
    capped_offer_blocks,
    derive_battery_pairs,
    same_price_same_bus_pairs,
)

type Key = tuple[str, ...]

SPD16_RISK_CLASSES = (
    "genRisk",
    "genRiskECE",
    "DCCE",
    "DCECE",
    "manual",
    "manualECE",
    "HVDCsecRisk",
    "HVDCsecRiskECE",
    "ACCELink",
    "ACECELink",
)
SPD16_CE_RISKS = frozenset({"genRisk", "DCCE", "manual", "HVDCsecRisk", "ACCELink"})
SPD16_LINK_RISKS = frozenset({"ACCELink", "ACECELink"})


@dataclass(frozen=True, slots=True)
class Spd16Case(ReserveCase):
    source_date: date = date(2026, 6, 23)
    capped_offer_block_mw: Mapping[Key, float] = field(default_factory=dict)
    tie_break_pairs: frozenset[Key] = frozenset()
    battery_pairs: frozenset[Key] = frozenset()
    tie_break_slack_price: float = 0.0001
    formulation_id: str = field(default=SPD16_FORMULATION_ID, init=False, repr=False)

    def __post_init__(self) -> None:
        super(Spd16Case, self).__post_init__()
        Spd16CompatibilityPolicy().validate(self.formulation_id, self.source_date)
        object.__setattr__(
            self,
            "capped_offer_block_mw",
            MappingProxyType(dict(self.capped_offer_block_mw)),
        )
        object.__setattr__(self, "tie_break_pairs", frozenset(self.tie_break_pairs))
        object.__setattr__(self, "battery_pairs", frozenset(self.battery_pairs))
        if set(self.capped_offer_block_mw) != set(self.offer_blocks):
            raise ValueError("v16 capped offer quantities must cover every offer block")
        if any(
            value <= 0.0
            for pair in self.tie_break_pairs
            for value in (
                self.capped_offer_block_mw[pair[:4]],
                self.capped_offer_block_mw[pair[:2] + pair[4:]],
            )
        ):
            raise ValueError("v16 tie-break denominators must be positive")

    @classmethod
    def from_reserve_case(
        cls,
        base: ReserveCase,
        *,
        source_date: date,
        capped_offer_block_mw: Mapping[Key, float] | None = None,
        tie_break_pairs: frozenset[Key] = frozenset(),
        battery_pairs: frozenset[Key] = frozenset(),
    ) -> Spd16Case:
        values = {
            item.name: getattr(base, item.name)
            for item in fields(ReserveCase)
            if item.init
        }
        reserve = base.reserve
        assert reserve is not None
        values["reserve"] = replace(
            reserve,
            risk_classes=SPD16_RISK_CLASSES,
            ce_risks=SPD16_CE_RISKS,
            ece_risks=frozenset(SPD16_RISK_CLASSES) - SPD16_CE_RISKS,
            link_risks=SPD16_LINK_RISKS,
            shareable_risks=reserve.generator_risks
            | reserve.manual_risks
            | SPD16_LINK_RISKS,
            group_risks=reserve.generator_risks | SPD16_LINK_RISKS,
        )
        capped = capped_offer_block_mw or {
            key: base.offer_limit[key] for key in base.offer_blocks
        }
        return cls(
            **values,
            source_date=source_date,
            capped_offer_block_mw=capped,
            tie_break_pairs=tie_break_pairs,
            battery_pairs=battery_pairs,
        )

    @classmethod
    def from_sources(
        cls,
        result: PreprocessingResult,
        case_data: CaseData,
    ) -> Spd16Case:
        source = CaseInput(case_data)
        source_date = source.gdx_date()
        Spd16CompatibilityPolicy().validate(SPD16_FORMULATION_ID, source_date)
        base = ReserveCase.from_sources(result, case_data)
        assert base.reserve is not None
        assert base.network is not None
        reserve = base.reserve

        risk_parameter = source.numeric("i_dateTimeRiskParameter")
        normalized_risk_parameter = {
            (key[:-1], key[-1].casefold()): value
            for key, value in risk_parameter.items()
        }
        free_input = {
            key[:-1]: value
            for key, value in risk_parameter.items()
            if key[-1].casefold() == "freereserve"
        }
        free_reserve = dict(reserve.free_reserve)
        effective = dict(reserve.effective_factor)
        for island in reserve.islands:
            for reserve_class in RESERVE_CLASSES:
                for risk in SPD16_LINK_RISKS:
                    key = (*island, reserve_class, risk)
                    free_reserve[key] = free_input.get(key, 0.0)
                    effective[key] = normalized_risk_parameter.get(
                        (key, "sharingeffectivefactor"), 0.0
                    )

        offer_parameter = source.numeric("i_dateTimeOfferParameter")
        secondary_offer = dict(reserve.secondary_risk_offer)
        for offer in base.offers:
            secondary_offer[(*offer, "ACCELink")] = offer_parameter.get(
                (*offer, "ACSecondaryCERiskMW"), 0.0
            )
            secondary_offer[(*offer, "ACECELink")] = offer_parameter.get(
                (*offer, "ACSecondaryECERiskMW"), 0.0
            )
        secondary_group = dict(reserve.secondary_risk_group)
        for ca, dt, _island, group, risk in reserve.island_risk_group:
            if risk not in SPD16_LINK_RISKS:
                continue
            secondary_group[(ca, dt, group, risk)] = sum(
                secondary_offer.get((ca, dt, offer, risk), 0.0)
                for r_ca, r_dt, r_group, offer, r_risk in reserve.risk_group_offer
                if (r_ca, r_dt, r_group, r_risk) == (ca, dt, group, risk)
            )
        upgraded_reserve = replace(
            reserve,
            free_reserve=free_reserve,
            effective_factor=effective,
            secondary_risk_offer=secondary_offer,
            secondary_risk_group=secondary_group,
        )
        base = replace(base, reserve=upgraded_reserve)
        network = base.network
        assert network is not None

        block_order = _uel_order(source, "i_dateTimeEnergyOffer", 3)
        offer_order = _uel_order(source, "i_dateTimeEnergyOffer", 2)
        potential = result.parameter("potential_mw").values
        capped = capped_offer_blocks(
            tuple(base.offer_blocks),
            offer_mw=base.offer_limit,
            reserve_generation_maximum=upgraded_reserve.reserve_generation_maximum,
            potential_mw=potential,
            generation_start=base.generation_start,
            ramp_rate_up=base.ramp_rate_up,
            interval_minutes=base.interval_minutes,
            block_order=block_order,
        )
        offer_bus = frozenset(
            (ca, dt, offer, bus)
            for ca, dt, offer, node in network.offer_node
            for n_ca, n_dt, n_node, bus in network.node_bus
            if (ca, dt, node) == (n_ca, n_dt, n_node)
        )
        tie_pairs = same_price_same_bus_pairs(
            tuple(base.offer_blocks),
            offer_price=base.offer_price,
            offer_bus=offer_bus,
            capped_mw=capped,
            offer_order=offer_order,
        )
        battery_pairs = _battery_pairs(result, case_data, base)
        return cls.from_reserve_case(
            base,
            source_date=source_date,
            capped_offer_block_mw=capped,
            tie_break_pairs=tie_pairs,
            battery_pairs=battery_pairs,
        )


def _uel_order(source: CaseInput, symbol: str, dimension: int) -> dict[str, int]:
    values = source.symbol(symbol).uel_orders[dimension]
    return {value: index for index, value in enumerate(values)}


def _battery_pairs(
    result: PreprocessingResult, case_data: CaseData, base: ReserveCase
) -> frozenset[Key]:
    source = CaseInput(case_data)
    assert base.network is not None
    bid_nodes = source.members("i_dateTimeBidNode")
    offer_nodes = source.members("i_dateTimeOfferNode")
    bid_traders = source.members("i_dateTimeBidTrader")
    offer_traders = source.members("i_dateTimeOfferTrader")
    load_like = {
        key[:2] + (node,)
        for key in result.set("demand_bid_block").members
        for ca, dt, bid, node in bid_nodes
        if key[:3] == (ca, dt, bid)
    }
    reserve_mw = result.parameter("reserve_offer_mw").values
    load_like.update(
        (ca, dt, node)
        for (
            ca,
            dt,
            offer,
            _block,
            _reserve_class,
            reserve_type,
        ), value in reserve_mw.items()
        for o_ca, o_dt, o_offer, node in offer_nodes
        if reserve_type == "ILRO"
        and value > 0.0
        and (ca, dt, offer) == (o_ca, o_dt, o_offer)
    )
    generation_nodes = {
        (ca, dt, node)
        for ca, dt, offer, node in offer_nodes
        if (ca, dt, offer) in base.offers
        and any(
            base.offer_limit[block] > 0.0
            for block in base.offer_blocks
            if block[:3] == (ca, dt, offer)
        )
    }
    bid_node_trader = {
        (ca, dt, node, trader)
        for ca, dt, bid, node in bid_nodes
        for t_ca, t_dt, t_bid, trader in bid_traders
        if (ca, dt, bid) == (t_ca, t_dt, t_bid)
    }
    offer_node_trader = {
        (ca, dt, node, trader)
        for ca, dt, offer, node in offer_nodes
        for t_ca, t_dt, t_offer, trader in offer_traders
        if (ca, dt, offer) == (t_ca, t_dt, t_offer)
    }
    return derive_battery_pairs(
        BatteryPairInputs(
            frozenset(load_like),
            frozenset(generation_nodes),
            frozenset(bid_node_trader),
            frozenset(offer_node_trader),
            source.members("i_busUnitAndKey3Match"),
        )
    )
