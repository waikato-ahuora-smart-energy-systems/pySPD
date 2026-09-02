"""Immutable normalized reserve, risk, NMIR, and scarcity inputs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from types import MappingProxyType

from pyspd.contracts import CaseData
from pyspd.hvdc.data import HvdcCase
from pyspd.preprocess import PreprocessingResult
from pyspd.preprocess.input import CaseInput, nonzero

type Key = tuple[str, ...]

RESERVE_FORMULATION_ID = "vspd-v5.0.6-reserve"
RESERVE_CLASSES = ("FIR", "SIR")
RESERVE_TYPES = ("PLRO", "TWRO", "ILRO")
RISK_CLASSES = (
    "genRisk",
    "genRiskECE",
    "DCCE",
    "DCECE",
    "manual",
    "manualECE",
    "HVDCsecRisk",
    "HVDCsecRiskECE",
)
CE_RISKS = frozenset({"genRisk", "DCCE", "manual", "HVDCsecRisk"})
ECE_RISKS = frozenset(set(RISK_CLASSES) - CE_RISKS)
GEN_RISKS = frozenset({"genRisk", "genRiskECE"})
MANUAL_RISKS = frozenset({"manual", "manualECE"})
HVDC_RISKS = frozenset({"DCCE", "DCECE"})
HVDC_SECONDARY_RISKS = frozenset({"HVDCsecRisk", "HVDCsecRiskECE"})
DIRECTIONS = ("forward", "backward")
ZONES = ("RP", "NR", "RZ")
BLOCKS = tuple(f"t{index}" for index in range(1, 21))
ENERGY_BREAKPOINTS = tuple(f"ls{index}" for index in range(1, 8))
RESERVE_BREAKPOINTS = tuple(f"ls{index}" for index in range(1, 14))


class ReserveDataError(ValueError):
    """Normalized reserve data violates a model invariant."""


def _proxy[K, V](values: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class ReserveData:
    islands: frozenset[Key]
    offer_island: frozenset[Key]
    risk_generators: frozenset[Key]
    primary_secondary_offer: frozenset[Key]
    risk_group_offer: frozenset[Key]
    island_risk_group: frozenset[Key]
    island_link_risk_group: frozenset[Key]
    directional_risk_factor: Mapping[Key, float]
    reserve_block_limit: Mapping[Key, float]
    reserve_block_price: Mapping[Key, float]
    reserve_offer_percent: Mapping[Key, float]
    reserve_generation_maximum: Mapping[Key, float]
    reserve_maximum_factor: Mapping[Key, float]
    risk_adjustment_factor: Mapping[Key, float]
    risk_minimum: Mapping[Key, float]
    free_reserve: Mapping[Key, float]
    hvdc_pole_ramp_up: Mapping[Key, float]
    secondary_risk_offer: Mapping[Key, float]
    secondary_risk_group: Mapping[Key, float]
    fk_band: Mapping[Key, float]
    hvdc_secondary_enabled: Mapping[Key, float]
    hvdc_secondary_subtractor: Mapping[Key, float]
    reserve_share_enabled: Mapping[Key, float]
    reserve_round_power: Mapping[Key, float]
    modulation_risk_class: Mapping[Key, float]
    modulation_risk: Mapping[Key, float]
    round_power_zone_exit: Mapping[Key, float]
    monopole_minimum: Mapping[Key, float]
    hvdc_control_band: Mapping[Key, float]
    hvdc_maximum: Mapping[Key, float]
    shared_nfr_maximum: Mapping[Key, float]
    effective_factor: Mapping[Key, float]
    energy_breakpoint_flow: Mapping[Key, float]
    energy_breakpoint_loss: Mapping[Key, float]
    reserve_breakpoint_flow: Mapping[Key, float]
    reserve_breakpoint_loss: Mapping[Key, float]
    reserve_scarcity_limit: Mapping[Key, float]
    reserve_scarcity_price: Mapping[Key, float]
    reserve_scarcity_enabled: Mapping[Key, float]
    market_reserve_offer_factor: Mapping[Key, float]
    market_reserve_bid_factor: Mapping[Key, float]
    offer_trader: Mapping[Key, str] = field(default_factory=dict)
    bid_trader: Mapping[Key, str] = field(default_factory=dict)
    big_m: float = 10_000.0
    deficit_reserve_ce_penalty: float = 100_000.0
    deficit_reserve_ece_penalty: float = 800_000.0
    enforce_nmir_sos2: bool = True
    risk_classes: tuple[str, ...] = RISK_CLASSES
    ce_risks: frozenset[str] = CE_RISKS
    ece_risks: frozenset[str] = ECE_RISKS
    generator_risks: frozenset[str] = GEN_RISKS
    manual_risks: frozenset[str] = MANUAL_RISKS
    hvdc_risks: frozenset[str] = HVDC_RISKS
    hvdc_secondary_risks: frozenset[str] = HVDC_SECONDARY_RISKS
    link_risks: frozenset[str] = frozenset()
    shareable_risks: frozenset[str] = GEN_RISKS | MANUAL_RISKS
    group_risks: frozenset[str] = GEN_RISKS

    def __post_init__(self) -> None:
        for name in (
            "islands",
            "offer_island",
            "risk_generators",
            "primary_secondary_offer",
            "risk_group_offer",
            "island_risk_group",
            "island_link_risk_group",
            "ce_risks",
            "ece_risks",
            "generator_risks",
            "manual_risks",
            "hvdc_risks",
            "hvdc_secondary_risks",
            "link_risks",
            "shareable_risks",
            "group_risks",
        ):
            object.__setattr__(self, name, frozenset(getattr(self, name)))
        object.__setattr__(self, "risk_classes", tuple(self.risk_classes))
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, Mapping):
                object.__setattr__(self, item.name, _proxy(value))
        numeric = (
            self.directional_risk_factor,
            self.reserve_block_limit,
            self.reserve_block_price,
            self.reserve_offer_percent,
            self.reserve_generation_maximum,
            self.reserve_maximum_factor,
            self.risk_adjustment_factor,
            self.risk_minimum,
            self.free_reserve,
            self.hvdc_pole_ramp_up,
            self.secondary_risk_offer,
            self.secondary_risk_group,
            self.fk_band,
            self.hvdc_secondary_enabled,
            self.hvdc_secondary_subtractor,
            self.reserve_share_enabled,
            self.reserve_round_power,
            self.modulation_risk_class,
            self.modulation_risk,
            self.round_power_zone_exit,
            self.monopole_minimum,
            self.hvdc_control_band,
            self.hvdc_maximum,
            self.shared_nfr_maximum,
            self.effective_factor,
            self.energy_breakpoint_flow,
            self.energy_breakpoint_loss,
            self.reserve_breakpoint_flow,
            self.reserve_breakpoint_loss,
            self.reserve_scarcity_limit,
            self.reserve_scarcity_price,
            self.reserve_scarcity_enabled,
        )
        if any(
            not math.isfinite(float(value))
            for mapping in numeric
            for value in mapping.values()
        ):
            raise ReserveDataError("all reserve numeric inputs must be finite")

    @classmethod
    def from_sources(
        cls,
        result: PreprocessingResult,
        case_data: CaseData,
        hvdc_case: HvdcCase,
    ) -> ReserveData:
        source = CaseInput(case_data)
        assert hvdc_case.network is not None
        assert hvdc_case.hvdc is not None
        network = hvdc_case.network
        periods = sorted(hvdc_case.periods)
        islands = frozenset(result.set("bus_island").members)
        island_domain = frozenset(
            (case, datetime, island) for case, datetime, _bus, island in islands
        )
        offer_island = result.set("offer_island").members
        offer_parameter = source.numeric("i_dateTimeOfferParameter")
        risk_generators = frozenset(
            (key[0], key[1], island, key[2])
            for key in hvdc_case.offers
            for o_case, o_dt, offer, island in offer_island
            if key == (o_case, o_dt, offer)
            and nonzero(offer_parameter.get((*key, "riskGenerator"), 0.0))
        )
        risk_group_offer = source.members("i_dateTimeRiskGroup")
        primary_secondary_offer = result.set("primary_secondary_offer").members
        island_risk_group = result.set("island_risk_group").members
        directional = result.parameter("directional_risk_factor").values
        island_link_groups = frozenset(
            (case, dt, island, group, risk)
            for case, dt, group, branch, risk in directional
            for b_case, b_dt, b_branch, bus in network.branch_from_bus
            for i_case, i_dt, i_bus, island in islands
            if (case, dt, branch) == (b_case, b_dt, b_branch)
            and (case, dt, bus) == (i_case, i_dt, i_bus)
        )
        reserve_limit = result.parameter("reserve_offer_mw").values
        reserve_price = result.parameter("reserve_offer_price").values
        all_reserve_blocks = {
            (*offer, block, reserve_class, reserve_type)
            for offer in hvdc_case.offers
            for block in BLOCKS
            for reserve_class in RESERVE_CLASSES
            for reserve_type in RESERVE_TYPES
        }
        reserve_block_limit = {
            key: reserve_limit.get(key, 0.0) for key in all_reserve_blocks
        }
        reserve_block_price = {
            key: reserve_price.get(key, 0.0) for key in all_reserve_blocks
        }
        reserve_percent = result.parameter("reserve_offer_percent").values
        reserve_generation_maximum = result.parameter(
            "reserve_generation_maximum"
        ).values
        reserve_maximum_factor = result.parameter("reserve_maximum_factor").values
        risk_parameter = source.numeric("i_dateTimeRiskParameter")
        risk_adjustment = result.parameter("risk_adjustment_factor").values
        risk_minimum = _risk_component(risk_parameter, "minRisk")
        hvdc_ramp = _risk_component(risk_parameter, "HVDCRampUp")
        effective = _risk_component(risk_parameter, "sharingEffectiveFactor")
        sharing = source.numeric("i_dateTimeReserveSharing")
        island_parameter = source.numeric("i_dateTimeIslandParameter")
        share_enabled = result.parameter("reserve_share_enabled").values
        round_power = result.parameter("reserve_round_power").values
        modulation_class: dict[Key, float] = {}
        modulation: dict[Key, float] = {}
        zone_exit: dict[Key, float] = {}
        monopole: dict[Key, float] = {}
        control: dict[Key, float] = {}
        for period in periods:
            ce = sharing.get((*period, "MRCE"), 0.0)
            ece = sharing.get((*period, "MRECE"), 0.0)
            for risk in RISK_CLASSES:
                modulation_class[(*period, risk)] = (
                    ce
                    if risk in {"DCCE", "HVDCsecRisk"}
                    else ece
                    if risk in {"DCECE", "HVDCsecRiskECE"}
                    else 0.0
                )
            modulation[period] = max(ce, ece)
            bipole = sharing.get((*period, "biPole2Mono"), 0.0)
            for reserve_class in RESERVE_CLASSES:
                zone_exit[(*period, reserve_class)] = bipole
            monopole[period] = sharing.get((*period, "monoPoleMin"), 0.0)
            control[(*period, "forward")] = sharing.get(
                (*period, "forwardHVDCcontrolBand"), 0.0
            )
            control[(*period, "backward")] = sharing.get(
                (*period, "backwardHVDCcontrolBand"), 0.0
            )
        hvdc_maximum = _hvdc_maximum(island_domain, islands, hvdc_case, source, result)
        energy_flow, energy_loss, reserve_flow, reserve_loss = _nmir_breakpoints(
            island_domain, islands, hvdc_case, source, sharing
        )
        shared_nfr = _shared_nfr_maximum(
            island_domain, result, hvdc_case, island_parameter, sharing
        )
        free_reserve_input = _risk_component(risk_parameter, "freeReserve")
        free_reserve: dict[Key, float] = {}
        for island in island_domain:
            for reserve_class in RESERVE_CLASSES:
                for risk in RISK_CLASSES:
                    value = free_reserve_input.get((*island, reserve_class, risk), 0.0)
                    if reserve_class == "FIR" and risk in GEN_RISKS | MANUAL_RISKS:
                        value -= sum(
                            shared_nfr[other]
                            for other in island_domain
                            if other[:2] == island[:2] and other != island
                        )
                    free_reserve[(*island, reserve_class, risk)] = value
        secondary_offer = {
            (*offer, risk): offer_parameter.get(
                (*offer, "ACSecondaryCERiskMW")
                if risk == "genRisk"
                else (*offer, "ACSecondaryECERiskMW"),
                0.0,
            )
            for offer in hvdc_case.offers
            for risk in GEN_RISKS
        }
        secondary_group: dict[Key, float] = {
            (case, dt, group, risk): sum(
                secondary_offer.get((case, dt, offer, risk), 0.0)
                for r_case, r_dt, r_group, offer, r_risk in risk_group_offer
                if (r_case, r_dt, r_group, r_risk) == (case, dt, group, risk)
            )
            for case, dt, _island, group, risk in island_risk_group
            if risk in GEN_RISKS
        }
        fk_band = {
            offer: offer_parameter.get((*offer, "FKbandMW"), 0.0)
            for offer in hvdc_case.offers
        }
        hvdc_secondary: dict[Key, float] = {
            (*island, risk): island_parameter.get((*island, risk), 0.0)
            for island in island_domain
            for risk in HVDC_SECONDARY_RISKS
        }
        hvdc_secondary_subtractor: dict[Key, float] = {
            island: island_parameter.get((*island, "HVDCSecSubtractor"), 0.0)
            for island in island_domain
        }
        reserve_scarcity_limit = result.parameter("scarcity_reserve_limit").values
        reserve_scarcity_price = result.parameter("scarcity_reserve_price").values
        reserve_scarcity_enabled = result.parameter("reserve_scarcity_enabled").values
        return cls(
            island_domain,
            offer_island,
            risk_generators,
            primary_secondary_offer,
            risk_group_offer,
            island_risk_group,
            island_link_groups,
            directional,
            reserve_block_limit,
            reserve_block_price,
            reserve_percent,
            reserve_generation_maximum,
            reserve_maximum_factor,
            risk_adjustment,
            risk_minimum,
            free_reserve,
            hvdc_ramp,
            secondary_offer,
            secondary_group,
            fk_band,
            hvdc_secondary,
            hvdc_secondary_subtractor,
            share_enabled,
            round_power,
            modulation_class,
            modulation,
            zone_exit,
            monopole,
            control,
            hvdc_maximum,
            shared_nfr,
            effective,
            energy_flow,
            energy_loss,
            reserve_flow,
            reserve_loss,
            reserve_scarcity_limit,
            reserve_scarcity_price,
            reserve_scarcity_enabled,
            source.numeric("i_dateTimeMNCnstrResrvFactors"),
            source.numeric("i_dateTimeMNCnstrResrvBidFactors"),
            offer_trader={
                key[:3]: key[3]
                for key in source.optional_members("i_dateTimeOfferTrader")
                if key[:3] in hvdc_case.offers
            },
            bid_trader={
                key[:3]: key[3]
                for key in source.optional_members("i_dateTimeBidTrader")
                if key[:3] in hvdc_case.bids
            },
        )


@dataclass(frozen=True, slots=True)
class ReserveCase(HvdcCase):
    reserve: ReserveData | None = None
    formulation_id: str = field(default=RESERVE_FORMULATION_ID, init=False, repr=False)

    def __post_init__(self) -> None:
        super(ReserveCase, self).__post_init__()
        if self.reserve is None:
            raise ReserveDataError("ReserveCase requires ReserveData")

    @classmethod
    def from_sources(
        cls,
        result: PreprocessingResult,
        case_data: CaseData,
    ) -> ReserveCase:
        hvdc = HvdcCase.from_sources(result, case_data)
        values = {
            item.name: getattr(hvdc, item.name)
            for item in fields(HvdcCase)
            if item.init
        }
        reserve = ReserveData.from_sources(result, case_data, hvdc)
        return cls(**values, reserve=reserve)


def _risk_component(values: Mapping[Key, float], component: str) -> dict[Key, float]:
    return {
        key[:-1]: value
        for key, value in values.items()
        if key[-1].casefold() == component.casefold()
    }


def _hvdc_maximum(
    island_domain: frozenset[Key],
    bus_island: frozenset[Key],
    case: HvdcCase,
    source: CaseInput,
    result: PreprocessingResult,
) -> dict[Key, float]:
    assert case.hvdc is not None
    data = case.hvdc
    factors = result.parameter("branch_constraint_limit").values
    senses = result.parameter("branch_constraint_sense").values
    branch_factors = source.numeric("i_dateTimeBranchConstraintFactors")
    ramping = source.component("i_dateTimeBranchConstraintRHS", "rampingCnstr")
    output: dict[Key, float] = {}
    for island in island_domain:
        sending = {
            link
            for link in data.links
            for *prefix, bus in data.sending_bus
            if tuple(prefix) == link and (*island[:2], bus, island[2]) in bus_island
        }
        monopoles: list[float] = []
        for link in sending:
            capacity = data.capacity[link]
            candidates = [
                factors[constraint]
                for constraint in factors
                if constraint[:2] == island[:2]
                and senses.get(constraint) == -1.0
                and not nonzero(ramping.get(constraint, 0.0))
                and sum(
                    branch_factors.get((*constraint, other[2]), 0.0)
                    for other in sending
                )
                == 1.0
                and branch_factors.get((*constraint, link[2]), 0.0) == 1.0
            ]
            monopoles.append(min([capacity, *candidates]))
        bipole_candidates = [
            factors[constraint]
            for constraint in factors
            if constraint[:2] == island[:2]
            and senses.get(constraint) == -1.0
            and not nonzero(ramping.get(constraint, 0.0))
            and sum(branch_factors.get((*constraint, link[2]), 0.0) for link in sending)
            == 2.0
        ]
        bipole = min(bipole_candidates, default=sum(data.capacity[x] for x in sending))
        output[island] = min(bipole, sum(monopoles))
    return output


def _nmir_breakpoints(
    island_domain: frozenset[Key],
    bus_island: frozenset[Key],
    case: HvdcCase,
    source: CaseInput,
    sharing: Mapping[Key, float],
) -> tuple[dict[Key, float], dict[Key, float], dict[Key, float], dict[Key, float]]:
    assert case.hvdc is not None
    data = case.hvdc
    resistance = source.component("i_dateTimeBranchParameter", "resistance")
    c, d, e, f = 0.14495, 0.32247, 0.46742, 0.82247
    fractions = (c, d, 0.5, 1.0 - d, 1.0 - c, 1.0)
    factor_coefficients = (0.75 * c, e, f, 2.0 - f, 2.0 - e, 2.0 - 0.75 * c)
    flow: dict[Key, float] = {}
    loss: dict[Key, float] = {}
    reserve_flow: dict[Key, float] = {}
    reserve_loss: dict[Key, float] = {}
    for island in island_domain:
        sending = [
            link
            for link in data.links
            for *prefix, bus in data.sending_bus
            if tuple(prefix) == link and (*island[:2], bus, island[2]) in bus_island
        ]
        capacity = sum(data.capacity[link] for link in sending)
        resistances = [resistance.get(link, 0.0) for link in sending]
        if len(resistances) == 2 and sum(resistances) != 0.0:
            aggregate_resistance = math.prod(resistances) / sum(resistances)
        else:
            aggregate_resistance = sum(resistances)
        segment_flow = [capacity * fraction for fraction in fractions]
        segment_factor = [
            0.01 * coefficient * aggregate_resistance * capacity
            for coefficient in factor_coefficients
        ]
        flows = [0.0, *segment_flow]
        losses = [0.0]
        scaling = sharing.get((*island[:2], "lossScalingFactorHVDC"), 0.0)
        for index in range(6):
            losses.append(
                losses[-1]
                + scaling * segment_factor[index] * (segment_flow[index] - flows[index])
            )
        for index, breakpoint in enumerate(ENERGY_BREAKPOINTS):
            flow[(*island, breakpoint)] = flows[index]
            loss[(*island, breakpoint)] = losses[index]
        signed_flows = [-value for value in reversed(flows)] + flows[1:]
        signed_losses = list(reversed(losses)) + losses[1:]
        for index, breakpoint in enumerate(RESERVE_BREAKPOINTS):
            reserve_flow[(*island, breakpoint)] = signed_flows[index]
            reserve_loss[(*island, breakpoint)] = signed_losses[index]
    return flow, loss, reserve_flow, reserve_loss


def _shared_nfr_maximum(
    island_domain: frozenset[Key],
    result: PreprocessingResult,
    case: HvdcCase,
    island_parameter: Mapping[Key, float],
    sharing: Mapping[Key, float],
) -> dict[Key, float]:
    required = result.parameter("required_load").values
    node_island = result.set("node_island").members
    bid_island = result.set("bid_island").members
    output: dict[Key, float] = {}
    for island in island_domain:
        load = sum(
            required.get((case_id, dt, node), 0.0)
            for case_id, dt, node, i_name in node_island
            if (case_id, dt, i_name) == island
        )
        bid = sum(
            case.bid_limit[block]
            for block in case.bid_blocks
            for b_case, b_dt, b_name, i_name in bid_island
            if block[:3] == (b_case, b_dt, b_name) and (b_case, b_dt, i_name) == island
        )
        offset = island_parameter.get((*island, "sharedNFRLoadOffset"), 0.0)
        rmt = island_parameter.get((*island, "RMTlimitFIR"), 0.0)
        factor = sharing.get((*island[:2], "sharedNFRfactor"), 0.0)
        output[island] = min(rmt, factor * (load + bid - offset))
    return output
