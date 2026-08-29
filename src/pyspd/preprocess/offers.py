"""Pure vSPD 5.0.6 offer, bid, and initial load preprocessing."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from pyspd.contracts import CaseData
from pyspd.preprocess.base import (
    Artifact,
    PreprocessingSettings,
    PreprocessingStep,
    SparseParameter,
    SparseSet,
)
from pyspd.preprocess.input import CaseInput, nonzero


class OfferBidLoadStep(PreprocessingStep):
    """Derive the market-participant domains consumed by the Pyomo model."""

    name = "offers_bids_load"
    requires = frozenset({"case_datetime", "node", "node_bus", "node_island"})
    provides = frozenset(
        {
            "study_mode",
            "interval_duration",
            "generation_start",
            "ramp_rate_up",
            "ramp_rate_down",
            "reserve_generation_maximum",
            "reserve_maximum_factor",
            "offer",
            "offer_island",
            "primary_offer",
            "secondary_offer",
            "primary_secondary_offer",
            "intermittent_offer",
            "price_responsive_offer",
            "potential_mw",
            "energy_offer_mw",
            "energy_offer_price",
            "generation_offer_block",
            "energy_offer_block_order",
            "positive_energy_offer",
            "reserve_offer_mw",
            "reserve_offer_price",
            "reserve_offer_percent",
            "reserve_offer_block",
            "reserve_offer_block_order",
            "bid",
            "bid_island",
            "demand_bid_mw",
            "demand_bid_price",
            "demand_bid_block",
            "demand_bid_block_order",
            "mapped_node",
            "input_initial_load",
            "target_total_load",
            "estimated_load_scalable",
            "estimated_non_scalable_load",
            "estimated_scalable_load",
            "estimated_scaling_factor",
            "estimated_initial_load",
            "initial_load",
            "load_scalable",
            "load_scaling_factor",
            "required_load",
        }
    )

    def apply(
        self,
        case_data: CaseData,
        artifacts: Mapping[str, Artifact],
        settings: PreprocessingSettings,
    ) -> Mapping[str, Artifact]:
        source = CaseInput(case_data)
        case_datetimes = _members(artifacts, "case_datetime")
        nodes = _members(artifacts, "node")
        node_bus = _members(artifacts, "node_bus")
        node_island = _members(artifacts, "node_island")

        run_mode = source.numeric("i_runMode")
        study_mode: dict[tuple[str, ...], float] = {
            (case, datetime): run_mode.get((case, "studyMode"), 0.0)
            for case, datetime in case_datetimes
        }
        interval_duration: dict[tuple[str, ...], float] = {
            (case, datetime): run_mode.get((case, "intervalLength"), 0.0)
            for case, datetime in case_datetimes
        }

        offer_parameter = source.numeric("i_dateTimeOfferParameter")
        initial = source.component("i_dateTimeOfferParameter", "initialMW")
        solved_initial = source.component("i_dateTimeOfferParameter", "solvedInitialMW")
        primary_secondary = source.members("i_dateTimePrimarySecondaryOffer")
        offer_identities = frozenset(key[:3] for key in offer_parameter)
        all_initial_zero: dict[tuple[str, str], bool] = {}
        for case, _datetime, offer in offer_identities:
            values = [
                value
                for (other_case, _other_datetime, other_offer), value in initial.items()
                if other_case == case and other_offer == offer
            ]
            all_initial_zero[(case, offer)] = bool(values) and all(
                value == 0.0 for value in values
            )

        generation_start: dict[tuple[str, ...], float] = {}
        for key in offer_identities:
            case, datetime, offer = key
            is_rtd = study_mode.get((case, datetime), 0.0) in {101.0, 201.0}
            use_initial = is_rtd or not settings.daily_mode
            value = (
                initial.get(key, 0.0) if use_initial else solved_initial.get(key, 0.0)
            )
            if not is_rtd and all_initial_zero.get((case, offer), False):
                value = solved_initial.get(key, 0.0)
            value += sum(
                initial.get((case, datetime, secondary), 0.0)
                for p_case, p_datetime, primary, secondary in primary_secondary
                if (p_case, p_datetime, primary) == key
            )
            generation_start[key] = value

        ramps_up = source.component("i_dateTimeOfferParameter", "rampUpRate")
        ramps_down = source.component("i_dateTimeOfferParameter", "rampDnRate")
        reserve_max = source.component("i_dateTimeOfferParameter", "resrvGenMax")
        intermittent = source.component("i_dateTimeOfferParameter", "isIG")
        responsive = source.component("i_dateTimeOfferParameter", "isPriceResponse")
        potential = source.component("i_dateTimeOfferParameter", "potentialMW")
        max_fir = source.component("i_dateTimeOfferParameter", "maxFactorFIR")
        max_sir = source.component("i_dateTimeOfferParameter", "maxFactorSIR")
        reserve_factor: dict[tuple[str, ...], float] = {}
        for key in offer_identities:
            reserve_factor[(*key, "FIR")] = max_fir.get(key, 0.0)
            reserve_factor[(*key, "SIR")] = max_sir.get(key, 0.0)
            if (
                nonzero(intermittent.get(key, 0.0))
                and nonzero(responsive.get(key, 0.0))
                and 0.0 < potential.get(key, 0.0) < reserve_max.get(key, 0.0)
            ):
                ratio = reserve_max[key] / potential[key]
                reserve_factor[(*key, "FIR")] = ratio
                reserve_factor[(*key, "SIR")] = ratio

        energy_limit = source.component("i_dateTimeEnergyOffer", "limitMW")
        energy_price = source.component("i_dateTimeEnergyOffer", "price")
        dispatchable_offer = source.component(
            "i_dateTimeOfferParameter", "dispatchable"
        )
        energy_mw = {
            key: value
            for key, value in energy_limit.items()
            if dispatchable_offer.get(key[:3], 0.0) == 1.0
        }
        energy_prices = {
            key: value
            for key, value in energy_price.items()
            if dispatchable_offer.get(key[:3], 0.0) == 1.0
        }

        reserve_limit = source.component("i_dateTimeReserveOffer", "limitMW")
        reserve_price_input = source.component("i_dateTimeReserveOffer", "price")
        reserve_percent_input = source.component("i_dateTimeReserveOffer", "plsrPct")
        reserve_mw = {_reserve_key(key): value for key, value in reserve_limit.items()}
        reserve_price = {
            _reserve_key(key): value for key, value in reserve_price_input.items()
        }
        reserve_percent = {
            _reserve_percent_key(key): value / 100.0
            for key, value in reserve_percent_input.items()
            if key[4] == "PLRO"
        }

        offer_node = source.members("i_dateTimeOfferNode")
        electrical = source.numeric("i_dateTimeBusElectricalIsland")
        valid_offers: set[tuple[str, ...]] = set()
        for case, datetime, offer, node in offer_node:
            if any(
                nonzero(electrical.get((case, datetime, bus), 0.0))
                for n_case, n_datetime, n_node, bus in node_bus
                if (n_case, n_datetime, n_node) == (case, datetime, node)
            ):
                valid_offers.add((case, datetime, offer))
        valid_offers.update(
            key[:3]
            for key, value in reserve_mw.items()
            if key[5] == "ILRO" and nonzero(value)
        )
        increase_limit = source.component("i_dateTimeParameter", "igIncreaseLimitRTD")
        for key in valid_offers:
            case, datetime, _offer = key
            if (
                study_mode.get((case, datetime), 0.0) in {101.0, 201.0}
                and nonzero(intermittent.get(key, 0.0))
                and nonzero(responsive.get(key, 0.0))
                and interval_duration.get((case, datetime), 0.0) > 0.0
            ):
                ramps_up[key] = min(
                    ramps_up.get(key, 0.0),
                    increase_limit.get((case, datetime), 0.0)
                    * 60.0
                    / interval_duration[(case, datetime)],
                )
        offer_island = frozenset(
            (case, datetime, offer, island)
            for case, datetime, offer, node in offer_node
            for i_case, i_datetime, i_node, island in node_island
            if (case, datetime, offer) in valid_offers
            and (i_case, i_datetime, i_node) == (case, datetime, node)
        )
        secondary = frozenset(
            (case, datetime, child)
            for case, datetime, _primary, child in primary_secondary
        )
        primary = frozenset(valid_offers - secondary)

        generation_blocks = frozenset(
            key for key, value in energy_mw.items() if value > 0.0
        )
        energy_block_position = _block_positions(
            source, "i_dateTimeEnergyOffer", 3, generation_blocks
        )
        positive_offers = frozenset(key[:3] for key in generation_blocks)
        reserve_blocks = frozenset(
            key for key, value in reserve_mw.items() if value > 0.0
        )
        reserve_block_position = {
            _reserve_key(key): value
            for key, value in _block_positions(
                source,
                "i_dateTimeReserveOffer",
                5,
                frozenset(reserve_limit),
            ).items()
            if _reserve_key(key) in reserve_blocks
        }

        bid_node = source.members("i_dateTimeBidNode")
        valid_bids = frozenset(
            (case, datetime, bid)
            for case, datetime, bid, node in bid_node
            if any(
                nonzero(electrical.get((case, datetime, bus), 0.0))
                for n_case, n_datetime, n_node, bus in node_bus
                if (n_case, n_datetime, n_node) == (case, datetime, node)
            )
        )
        bid_island = frozenset(
            (case, datetime, bid, island)
            for case, datetime, bid, node in bid_node
            for i_case, i_datetime, i_node, island in node_island
            if (case, datetime, bid) in valid_bids
            and (i_case, i_datetime, i_node) == (case, datetime, node)
        )
        dispatchable_bid = source.component("i_dateTimeBidParameter", "dispatchable")
        bid_limit = source.component("i_dateTimeEnergyBid", "limitMW")
        bid_price_input = source.component("i_dateTimeEnergyBid", "price")
        demand_mw = {
            key: value
            for key, value in bid_limit.items()
            if key[:3] in valid_bids and dispatchable_bid.get(key[:3], 0.0) == 1.0
        }
        demand_price = {
            key: value
            for key, value in bid_price_input.items()
            if key[:3] in valid_bids and dispatchable_bid.get(key[:3], 0.0) == 1.0
        }
        demand_blocks = frozenset(
            key for key, value in demand_mw.items() if nonzero(value)
        )
        demand_block_position = _block_positions(
            source, "i_dateTimeEnergyBid", 3, demand_blocks
        )

        demand = source.component("i_dateTimeNodeParameter", "demand")
        difference_bid = source.component("i_dateTimeBidParameter", "difference")
        required_load = {key: demand.get(key, 0.0) for key in nodes}
        bid_totals: dict[tuple[str, ...], float] = defaultdict(float)
        for key, value in demand_mw.items():
            bid_totals[key[:3]] += value
        for case, datetime, bid, node in bid_node:
            bid_key = (case, datetime, bid)
            if difference_bid.get(bid_key, 0.0) == 0.0 and bid_totals[bid_key] > 0.0:
                required_load[(case, datetime, node)] = 0.0

        mapped_node = source.optional_members("i_dateTimeNodetoNode")
        input_initial = source.component("i_dateTimeNodeParameter", "initialLoad")
        conforming = source.component("i_dateTimeNodeParameter", "conformingFactor")
        nonconforming = source.component(
            "i_dateTimeNodeParameter", "nonConformingFactor"
        )
        load_override = source.component("i_dateTimeNodeParameter", "loadIsOverride")
        bad_load = source.component("i_dateTimeNodeParameter", "loadIsBad")
        ncl = source.component("i_dateTimeNodeParameter", "loadIsNCL")
        maximum_load = source.component("i_dateTimeNodeParameter", "maxLoad")
        instructed_shed = source.component(
            "i_dateTimeNodeParameter", "instructedLoadShed"
        )
        shed_active = source.component(
            "i_dateTimeNodeParameter", "instructedShedActive"
        )
        dispatched_load = source.component("i_dateTimeNodeParameter", "dispatchedLoad")
        dispatched_generation = source.component(
            "i_dateTimeNodeParameter", "dispatchedGeneration"
        )
        use_actual = source.component("i_dateTimeParameter", "useActualLoad")
        island_mwips = source.component("i_dateTimeIslandParameter", "MWIPS")
        island_pds = source.component("i_dateTimeIslandParameter", "PSD")
        island_losses = source.component("i_dateTimeIslandParameter", "Losses")
        spd_load_losses = source.component(
            "i_dateTimeIslandParameter", "SPDLoadCalcLosses"
        )
        islands = frozenset(key[:2] + (key[3],) for key in node_island)
        target_total: dict[tuple[str, ...], float] = {}
        est_scalable: dict[tuple[str, ...], float] = {key: 0.0 for key in nodes}
        est_non_scalable: dict[tuple[str, ...], float] = {key: 0.0 for key in nodes}
        est_scalable_load: dict[tuple[str, ...], float] = {key: 0.0 for key in nodes}
        est_scaling: dict[tuple[str, ...], float] = {key: 0.0 for key in islands}
        estimated_initial: dict[tuple[str, ...], float] = {
            key: input_initial.get(key, 0.0) for key in nodes
        }
        initial_load: dict[tuple[str, ...], float] = dict(estimated_initial)
        load_scalable: dict[tuple[str, ...], float] = {key: 0.0 for key in nodes}
        load_scaling: dict[tuple[str, ...], float] = {key: 0.0 for key in islands}
        if settings.apply_rtd_load_reconstruction:
            _reconstruct_rtd_load(
                nodes=nodes,
                node_island=node_island,
                study_mode=study_mode,
                daily_mode=settings.daily_mode,
                use_actual=use_actual,
                input_initial=input_initial,
                conforming=conforming,
                nonconforming=nonconforming,
                load_override=load_override,
                bad_load=bad_load,
                ncl=ncl,
                maximum_load=maximum_load,
                instructed_shed=instructed_shed,
                shed_active=shed_active,
                dispatched_load=dispatched_load,
                dispatched_generation=dispatched_generation,
                island_mwips=island_mwips,
                island_pds=island_pds,
                island_losses=island_losses,
                spd_load_losses=spd_load_losses,
                target_total=target_total,
                est_scalable=est_scalable,
                est_non_scalable=est_non_scalable,
                est_scalable_load=est_scalable_load,
                est_scaling=est_scaling,
                estimated_initial=estimated_initial,
                initial_load=initial_load,
                load_scalable=load_scalable,
                load_scaling=load_scaling,
                required_load=required_load,
            )

        offer_dims = ("case", "datetime", "offer")
        offer_block_dims = (*offer_dims, "block")
        reserve_dims = (*offer_dims, "block", "reserve_class", "reserve_type")
        bid_dims = ("case", "datetime", "bid")
        bid_block_dims = (*bid_dims, "block")
        return {
            "study_mode": SparseParameter(
                "study_mode", ("case", "datetime"), study_mode
            ),
            "interval_duration": SparseParameter(
                "interval_duration", ("case", "datetime"), interval_duration
            ),
            "generation_start": SparseParameter(
                "generation_start", offer_dims, generation_start
            ),
            "ramp_rate_up": SparseParameter("ramp_rate_up", offer_dims, ramps_up),
            "ramp_rate_down": SparseParameter("ramp_rate_down", offer_dims, ramps_down),
            "reserve_generation_maximum": SparseParameter(
                "reserve_generation_maximum", offer_dims, reserve_max
            ),
            "reserve_maximum_factor": SparseParameter(
                "reserve_maximum_factor", (*offer_dims, "reserve_class"), reserve_factor
            ),
            "offer": SparseSet("offer", offer_dims, frozenset(valid_offers)),
            "offer_island": SparseSet(
                "offer_island", (*offer_dims, "island"), offer_island
            ),
            "primary_offer": SparseSet("primary_offer", offer_dims, primary),
            "secondary_offer": SparseSet("secondary_offer", offer_dims, secondary),
            "primary_secondary_offer": SparseSet(
                "primary_secondary_offer",
                (*offer_dims, "secondary_offer"),
                primary_secondary,
            ),
            "intermittent_offer": SparseSet(
                "intermittent_offer",
                offer_dims,
                frozenset(key for key in valid_offers if nonzero(intermittent.get(key, 0.0))),
            ),
            "price_responsive_offer": SparseSet(
                "price_responsive_offer",
                offer_dims,
                frozenset(key for key in valid_offers if nonzero(responsive.get(key, 0.0))),
            ),
            "potential_mw": SparseParameter("potential_mw", offer_dims, potential),
            "energy_offer_mw": SparseParameter(
                "energy_offer_mw", offer_block_dims, energy_mw
            ),
            "energy_offer_price": SparseParameter(
                "energy_offer_price", offer_block_dims, energy_prices
            ),
            "generation_offer_block": SparseSet(
                "generation_offer_block", offer_block_dims, generation_blocks
            ),
            "energy_offer_block_order": SparseParameter(
                "energy_offer_block_order", offer_block_dims, energy_block_position
            ),
            "positive_energy_offer": SparseSet(
                "positive_energy_offer", offer_dims, positive_offers
            ),
            "reserve_offer_mw": SparseParameter(
                "reserve_offer_mw", reserve_dims, reserve_mw
            ),
            "reserve_offer_price": SparseParameter(
                "reserve_offer_price", reserve_dims, reserve_price
            ),
            "reserve_offer_percent": SparseParameter(
                "reserve_offer_percent",
                (*offer_dims, "block", "reserve_class"),
                reserve_percent,
            ),
            "reserve_offer_block": SparseSet(
                "reserve_offer_block", reserve_dims, reserve_blocks
            ),
            "reserve_offer_block_order": SparseParameter(
                "reserve_offer_block_order", reserve_dims, reserve_block_position
            ),
            "bid": SparseSet("bid", bid_dims, valid_bids),
            "bid_island": SparseSet("bid_island", (*bid_dims, "island"), bid_island),
            "demand_bid_mw": SparseParameter(
                "demand_bid_mw", bid_block_dims, demand_mw
            ),
            "demand_bid_price": SparseParameter(
                "demand_bid_price", bid_block_dims, demand_price
            ),
            "demand_bid_block": SparseSet(
                "demand_bid_block", bid_block_dims, demand_blocks
            ),
            "demand_bid_block_order": SparseParameter(
                "demand_bid_block_order", bid_block_dims, demand_block_position
            ),
            "mapped_node": SparseSet(
                "mapped_node", ("case", "datetime", "node", "mapped_node"), mapped_node
            ),
            "input_initial_load": SparseParameter(
                "input_initial_load", ("case", "datetime", "node"), input_initial
            ),
            "target_total_load": SparseParameter(
                "target_total_load", ("case", "datetime", "island"), target_total
            ),
            "estimated_load_scalable": SparseParameter(
                "estimated_load_scalable", ("case", "datetime", "node"), est_scalable
            ),
            "estimated_non_scalable_load": SparseParameter(
                "estimated_non_scalable_load",
                ("case", "datetime", "node"),
                est_non_scalable,
            ),
            "estimated_scalable_load": SparseParameter(
                "estimated_scalable_load",
                ("case", "datetime", "node"),
                est_scalable_load,
            ),
            "estimated_scaling_factor": SparseParameter(
                "estimated_scaling_factor",
                ("case", "datetime", "island"),
                est_scaling,
            ),
            "estimated_initial_load": SparseParameter(
                "estimated_initial_load",
                ("case", "datetime", "node"),
                estimated_initial,
            ),
            "initial_load": SparseParameter(
                "initial_load", ("case", "datetime", "node"), initial_load
            ),
            "load_scalable": SparseParameter(
                "load_scalable", ("case", "datetime", "node"), load_scalable
            ),
            "load_scaling_factor": SparseParameter(
                "load_scaling_factor",
                ("case", "datetime", "island"),
                load_scaling,
            ),
            "required_load": SparseParameter(
                "required_load", ("case", "datetime", "node"), required_load
            ),
        }


def _members(
    artifacts: Mapping[str, Artifact], name: str
) -> frozenset[tuple[str, ...]]:
    artifact = artifacts[name]
    if not isinstance(artifact, SparseSet):
        raise TypeError(name)
    return artifact.members


def _reserve_key(key: tuple[str, ...]) -> tuple[str, ...]:
    case, datetime, offer, reserve_class, reserve_type, block = key
    return case, datetime, offer, block, reserve_class, reserve_type


def _reserve_percent_key(key: tuple[str, ...]) -> tuple[str, ...]:
    case, datetime, offer, reserve_class, _reserve_type, block = key
    return case, datetime, offer, block, reserve_class


def _block_positions(
    source: CaseInput,
    symbol_name: str,
    block_dimension: int,
    domain: frozenset[tuple[str, ...]],
) -> dict[tuple[str, ...], float]:
    order = {
        block: float(position)
        for position, block in enumerate(
            source.symbol(symbol_name).uel_orders[block_dimension], start=1
        )
    }
    return {key: order[key[block_dimension]] for key in domain}


def _reconstruct_rtd_load(
    *,
    nodes: frozenset[tuple[str, ...]],
    node_island: frozenset[tuple[str, ...]],
    study_mode: dict[tuple[str, ...], float],
    daily_mode: bool,
    use_actual: dict[tuple[str, ...], float],
    input_initial: dict[tuple[str, ...], float],
    conforming: dict[tuple[str, ...], float],
    nonconforming: dict[tuple[str, ...], float],
    load_override: dict[tuple[str, ...], float],
    bad_load: dict[tuple[str, ...], float],
    ncl: dict[tuple[str, ...], float],
    maximum_load: dict[tuple[str, ...], float],
    instructed_shed: dict[tuple[str, ...], float],
    shed_active: dict[tuple[str, ...], float],
    dispatched_load: dict[tuple[str, ...], float],
    dispatched_generation: dict[tuple[str, ...], float],
    island_mwips: dict[tuple[str, ...], float],
    island_pds: dict[tuple[str, ...], float],
    island_losses: dict[tuple[str, ...], float],
    spd_load_losses: dict[tuple[str, ...], float],
    target_total: dict[tuple[str, ...], float],
    est_scalable: dict[tuple[str, ...], float],
    est_non_scalable: dict[tuple[str, ...], float],
    est_scalable_load: dict[tuple[str, ...], float],
    est_scaling: dict[tuple[str, ...], float],
    estimated_initial: dict[tuple[str, ...], float],
    initial_load: dict[tuple[str, ...], float],
    load_scalable: dict[tuple[str, ...], float],
    load_scaling: dict[tuple[str, ...], float],
    required_load: dict[tuple[str, ...], float],
) -> None:
    islands = sorted({key[:2] + (key[3],) for key in node_island})
    for island_key in islands:
        case, datetime, _island = island_key
        if study_mode.get((case, datetime), 0.0) not in {101.0, 201.0}:
            continue
        island_nodes = {
            (n_case, n_datetime, node)
            for n_case, n_datetime, node, n_island in node_island
            if (n_case, n_datetime, n_island) == island_key
        }
        losses = (
            spd_load_losses.get(island_key, 0.0)
            if daily_mode
            else island_losses.get(island_key, 0.0)
        )
        target_total[island_key] = (
            island_mwips.get(island_key, 0.0)
            + island_pds.get(island_key, 0.0)
            - losses
            + sum(
                dispatched_generation.get(node, 0.0) - dispatched_load.get(node, 0.0)
                for node in island_nodes
            )
        )
        for node in island_nodes:
            scalable = ncl.get(node, 0.0) == 0.0 and conforming.get(node, 0.0) > 0.0
            est_scalable[node] = float(scalable)
            est_non_scalable[node] = (
                nonconforming.get(node, 0.0)
                if ncl.get(node, 0.0) == 1.0
                else conforming.get(node, 0.0)
            )
            if scalable:
                est_non_scalable[node] = 0.0
                est_scalable_load[node] = conforming.get(node, 0.0)
        est_denominator = sum(est_scalable_load[node] for node in island_nodes)
        est_numerator = (
            island_mwips.get(island_key, 0.0)
            - losses
            - sum(est_non_scalable[node] for node in island_nodes)
        )
        est_scaling[island_key] = (
            est_numerator / est_denominator if est_denominator != 0.0 else 0.0
        )
        for node in island_nodes:
            estimated_initial[node] = (
                conforming.get(node, 0.0) * est_scaling[island_key]
                if est_scalable[node] == 1.0
                else est_non_scalable[node]
            )
            initial_load[node] = input_initial.get(node, 0.0)
            if load_override.get(node, 0.0) == 0.0 and (
                use_actual.get((case, datetime), 0.0) == 0.0
                or bad_load.get(node, 0.0) == 1.0
            ):
                initial_load[node] = estimated_initial[node]
            if (
                load_override.get(node, 0.0) == 1.0
                and use_actual.get((case, datetime), 0.0) == 1.0
                and initial_load[node] > maximum_load.get(node, 0.0)
            ):
                initial_load[node] = maximum_load.get(node, 0.0)
            load_scalable[node] = float(
                ncl.get(node, 0.0) == 0.0
                and load_override.get(node, 0.0) == 0.0
                and initial_load[node] >= 0.0
            )
        load_denominator = sum(
            initial_load[node] for node in island_nodes if load_scalable[node] == 1.0
        )
        load_numerator = target_total[island_key] - sum(
            initial_load[node] for node in island_nodes if load_scalable[node] == 0.0
        )
        load_scaling[island_key] = (
            load_numerator / load_denominator if load_denominator != 0.0 else 0.0
        )
        for node in island_nodes:
            required_load[node] = (
                initial_load[node] * load_scaling[island_key]
                if load_scalable[node] == 1.0
                else initial_load[node]
            )
            if shed_active.get(node, 0.0) != 0.0:
                required_load[node] += instructed_shed.get(node, 0.0)
