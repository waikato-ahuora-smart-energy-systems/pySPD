"""Branch, market-node, risk, reserve-sharing, and scarcity preprocessing."""

from __future__ import annotations

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


class ConstraintRiskStep(PreprocessingStep):
    """Build the constraint/risk domains after topology and participant filtering."""

    name = "constraints_risk_scarcity"
    requires = frozenset(
        {
            "branch",
            "offer",
            "bid",
            "offer_island",
            "directional_risk_factor",
            "case_datetime",
            "node",
            "required_load",
        }
    )
    provides = frozenset(
        {
            "branch_constraint",
            "branch_constraint_sense",
            "branch_constraint_limit",
            "branch_constraint_ramping",
            "market_node_constraint",
            "market_node_constraint_sense",
            "market_node_constraint_limit",
            "island_risk_group",
            "risk_adjustment_factor",
            "reserve_share_enabled",
            "reserve_round_power",
            "round_power_zone_exit",
            "energy_scarcity_enabled",
            "reserve_scarcity_enabled",
            "bad_price_factor",
            "scarcity_energy_price_max",
            "scarcity_energy_block",
            "scarcity_energy_fixed_limit_block",
            "scarcity_energy_load_factor",
            "scarcity_energy_limit",
            "scarcity_energy_price",
            "scarcity_reserve_limit",
            "scarcity_reserve_price",
        }
    )

    def apply(
        self,
        case_data: CaseData,
        artifacts: Mapping[str, Artifact],
        settings: PreprocessingSettings,
    ) -> Mapping[str, Artifact]:
        source = CaseInput(case_data)
        branches = _members(artifacts, "branch")
        offers = _members(artifacts, "offer")
        bids = _members(artifacts, "bid")
        offer_island = _members(artifacts, "offer_island")
        case_datetimes = _members(artifacts, "case_datetime")
        nodes = _members(artifacts, "node")
        required_load_artifact = artifacts["required_load"]
        if not isinstance(required_load_artifact, SparseParameter):
            raise TypeError("required_load")

        branch_factors = source.numeric("i_dateTimeBranchConstraintFactors")
        branch_constraints = frozenset(
            key[:3]
            for key, value in branch_factors.items()
            if nonzero(value) and key[0:2] + (key[3],) in branches
        )
        branch_rhs = source.numeric("i_dateTimeBranchConstraintRHS")
        branch_sense = _rhs_component(branch_rhs, "cnstrSense", branch_constraints)
        branch_limit = _rhs_component(branch_rhs, "cnstrLimit", branch_constraints)
        branch_ramping = frozenset(
            key
            for key, value in _rhs_component(
                branch_rhs, "rampingCnstr", branch_constraints
            ).items()
            if nonzero(value)
        )

        energy_offer_factor = source.numeric("i_dateTimeMNCnstrEnrgFactors")
        reserve_offer_factor = source.numeric("i_dateTimeMNCnstrResrvFactors")
        energy_bid_factor = source.numeric("i_dateTimeMNCnstrEnrgBidFactors")
        reserve_bid_factor = source.numeric("i_dateTimeMNCnstrResrvBidFactors")
        market_constraints = {
            key[:3]
            for key, value in energy_offer_factor.items()
            if nonzero(value) and key[:2] + (key[3],) in offers
        }
        market_constraints.update(
            key[:3]
            for key, value in reserve_offer_factor.items()
            if nonzero(value) and key[:2] + (key[3],) in offers
        )
        market_constraints.update(
            key[:3]
            for key, value in energy_bid_factor.items()
            if nonzero(value) and key[:2] + (key[3],) in bids
        )
        market_constraints.update(
            key[:3]
            for key, value in reserve_bid_factor.items()
            if nonzero(value) and key[:2] + (key[3],) in bids
        )
        market_constraints_frozen = frozenset(market_constraints)
        market_rhs = source.numeric("i_dateTimeMNCnstrRHS")
        market_sense = _rhs_component(
            market_rhs, "cnstrSense", market_constraints_frozen
        )
        market_limit = _rhs_component(
            market_rhs, "cnstrLimit", market_constraints_frozen
        )

        risk_group_offer = source.members("i_dateTimeRiskGroup")
        island_risk_groups = frozenset(
            (case, datetime, island, risk_group, risk_class)
            for case, datetime, risk_group, offer, risk_class in risk_group_offer
            for o_case, o_datetime, o_offer, island in offer_island
            if (case, datetime, offer) == (o_case, o_datetime, o_offer)
        )
        risk_adjustment_input = source.numeric("i_dateTimeRiskParameter")
        risk_adjustment = {
            key[:-1]: value * float(settings.use_reserve_model)
            for key, value in risk_adjustment_input.items()
            if key[-1].casefold() == "adjustfactor"
        }

        sharing = source.numeric("i_dateTimeReserveSharing")
        share_enabled: dict[tuple[str, ...], float] = {}
        round_power: dict[tuple[str, ...], float] = {}
        zone_exit: dict[tuple[str, ...], float] = {}
        use_bipole = _scalar(artifacts, "fir_uses_bipole_transition") != 0.0
        for case, datetime in case_datetimes:
            prefix = (case, datetime)
            share_enabled[(*prefix, "FIR")] = sharing.get((*prefix, "sharingFIR"), 0.0)
            share_enabled[(*prefix, "SIR")] = sharing.get((*prefix, "sharingSIR"), 0.0)
            round_power[(*prefix, "FIR")] = sharing.get((*prefix, "roundPwrFIR"), 0.0)
            round_power[(*prefix, "SIR")] = sharing.get((*prefix, "roundPwrSIR"), 0.0)
            modulation = max(
                sharing.get((*prefix, "MRCE"), 0.0),
                sharing.get((*prefix, "MRECE"), 0.0),
            )
            bipole = sharing.get((*prefix, "biPole2Mono"), 0.0)
            fir = sharing.get((*prefix, "roundPwr2Mono"), 0.0) - modulation
            zone_exit[(*prefix, "FIR")] = bipole if use_bipole else fir
            zone_exit[(*prefix, "SIR")] = bipole

        datetime_parameters = source.numeric("i_dateTimeParameter")
        energy_scarcity = _datetime_component(
            datetime_parameters, "enrgScarcity", case_datetimes
        )
        reserve_scarcity = _datetime_component(
            datetime_parameters, "resrvScarcity", case_datetimes
        )
        bad_price = _datetime_component(
            datetime_parameters, "badPriceFactor", case_datetimes
        )
        bad_price = {
            key: value if nonzero(value) else 5.0 for key, value in bad_price.items()
        }
        national_price = source.component("i_dateTimeScarcityNationalFactor", "price")
        national_factor = source.component("i_dateTimeScarcityNationalFactor", "factor")
        scarcity_price_max = {
            key: max(
                (
                    value
                    for price_key, value in national_price.items()
                    if price_key[:2] == key
                ),
                default=0.0,
            )
            for key in case_datetimes
        }
        reserve_limit_input = source.component(
            "i_dateTimeScarcityResrvLimit", "limitMW"
        )
        reserve_price_input = source.component("i_dateTimeScarcityResrvLimit", "price")
        node_limit_input = source.optional_component(
            "i_dateTimeScarcityNodeLimit", "limitMW"
        )
        node_limit_price = source.optional_component(
            "i_dateTimeScarcityNodeLimit", "price"
        )
        node_factor_input = source.optional_component(
            "i_dateTimeScarcityNodeFactor", "factor"
        )
        node_factor_price = source.optional_component(
            "i_dateTimeScarcityNodeFactor", "price"
        )
        energy_blocks = frozenset(
            (*node, f"t{block}") for node in nodes for block in range(1, 21)
        )
        energy_limit_input: dict[tuple[str, ...], float] = {}
        energy_load_factor: dict[tuple[str, ...], float] = {}
        energy_price_input: dict[tuple[str, ...], float] = {}
        energy_fixed_limit_blocks: set[tuple[str, ...]] = set()
        for key in energy_blocks:
            case, datetime, _node, block = key
            enabled = nonzero(energy_scarcity.get((case, datetime), 0.0))
            load = required_load_artifact.get(key[:3])
            limit = (
                national_factor.get((case, datetime, block), 0.0) * load
                if enabled and load > 0.0
                else 0.0
            )
            load_factor = (
                national_factor.get((case, datetime, block), 0.0) if enabled else 0.0
            )
            price = national_price.get((case, datetime, block), 0.0) if enabled else 0.0
            if enabled and load > 0.0 and nonzero(node_factor_input.get(key, 0.0)):
                limit = node_factor_input[key] * load
            if enabled and nonzero(node_factor_input.get(key, 0.0)):
                load_factor = node_factor_input[key]
            if enabled and nonzero(node_factor_price.get(key, 0.0)):
                price = node_factor_price[key]
            if enabled and nonzero(node_limit_input.get(key, 0.0)):
                limit = node_limit_input[key]
                energy_fixed_limit_blocks.add(key)
            if enabled and nonzero(node_limit_price.get(key, 0.0)):
                price = node_limit_price[key]
            energy_limit_input[key] = limit
            energy_load_factor[key] = load_factor
            energy_price_input[key] = price

        branch_dims = ("case", "datetime", "branch_constraint")
        market_dims = ("case", "datetime", "market_node_constraint")
        return {
            "branch_constraint": SparseSet(
                "branch_constraint", branch_dims, branch_constraints
            ),
            "branch_constraint_sense": SparseParameter(
                "branch_constraint_sense", branch_dims, branch_sense
            ),
            "branch_constraint_limit": SparseParameter(
                "branch_constraint_limit", branch_dims, branch_limit
            ),
            "branch_constraint_ramping": SparseSet(
                "branch_constraint_ramping", branch_dims, branch_ramping
            ),
            "market_node_constraint": SparseSet(
                "market_node_constraint", market_dims, market_constraints_frozen
            ),
            "market_node_constraint_sense": SparseParameter(
                "market_node_constraint_sense", market_dims, market_sense
            ),
            "market_node_constraint_limit": SparseParameter(
                "market_node_constraint_limit", market_dims, market_limit
            ),
            "island_risk_group": SparseSet(
                "island_risk_group",
                ("case", "datetime", "island", "risk_group", "risk_class"),
                island_risk_groups,
            ),
            "risk_adjustment_factor": SparseParameter(
                "risk_adjustment_factor",
                ("case", "datetime", "island", "reserve_class", "risk_class"),
                risk_adjustment,
            ),
            "reserve_share_enabled": SparseParameter(
                "reserve_share_enabled",
                ("case", "datetime", "reserve_class"),
                share_enabled,
            ),
            "reserve_round_power": SparseParameter(
                "reserve_round_power",
                ("case", "datetime", "reserve_class"),
                round_power,
            ),
            "round_power_zone_exit": SparseParameter(
                "round_power_zone_exit",
                ("case", "datetime", "reserve_class"),
                zone_exit,
            ),
            "energy_scarcity_enabled": SparseParameter(
                "energy_scarcity_enabled", ("case", "datetime"), energy_scarcity
            ),
            "reserve_scarcity_enabled": SparseParameter(
                "reserve_scarcity_enabled", ("case", "datetime"), reserve_scarcity
            ),
            "bad_price_factor": SparseParameter(
                "bad_price_factor", ("case", "datetime"), bad_price
            ),
            "scarcity_energy_price_max": SparseParameter(
                "scarcity_energy_price_max",
                ("case", "datetime"),
                scarcity_price_max,
            ),
            "scarcity_energy_block": SparseSet(
                "scarcity_energy_block",
                ("case", "datetime", "node", "block"),
                energy_blocks,
            ),
            "scarcity_energy_fixed_limit_block": SparseSet(
                "scarcity_energy_fixed_limit_block",
                ("case", "datetime", "node", "block"),
                frozenset(energy_fixed_limit_blocks),
            ),
            "scarcity_energy_load_factor": SparseParameter(
                "scarcity_energy_load_factor",
                ("case", "datetime", "node", "block"),
                energy_load_factor,
            ),
            "scarcity_energy_limit": SparseParameter(
                "scarcity_energy_limit",
                ("case", "datetime", "node", "block"),
                energy_limit_input,
            ),
            "scarcity_energy_price": SparseParameter(
                "scarcity_energy_price",
                ("case", "datetime", "node", "block"),
                energy_price_input,
            ),
            "scarcity_reserve_limit": SparseParameter(
                "scarcity_reserve_limit",
                ("case", "datetime", "island", "reserve_class", "block"),
                reserve_limit_input,
            ),
            "scarcity_reserve_price": SparseParameter(
                "scarcity_reserve_price",
                ("case", "datetime", "island", "reserve_class", "block"),
                reserve_price_input,
            ),
        }


def _members(
    artifacts: Mapping[str, Artifact], name: str
) -> frozenset[tuple[str, ...]]:
    artifact = artifacts[name]
    if not isinstance(artifact, SparseSet):
        raise TypeError(name)
    return artifact.members


def _scalar(artifacts: Mapping[str, Artifact], name: str) -> float:
    artifact = artifacts[name]
    if not isinstance(artifact, SparseParameter):
        raise TypeError(name)
    return artifact.get(())


def _rhs_component(
    values: dict[tuple[str, ...], float],
    component: str,
    domain: frozenset[tuple[str, ...]],
) -> dict[tuple[str, ...], float]:
    return {
        key[:-1]: value
        for key, value in values.items()
        if key[-1].casefold() == component.casefold() and key[:-1] in domain
    }


def _datetime_component(
    values: dict[tuple[str, ...], float],
    component: str,
    domain: frozenset[tuple[str, ...]],
) -> dict[tuple[str, ...], float]:
    selected = {
        key[:-1]: value
        for key, value in values.items()
        if key[-1].casefold() == component.casefold()
    }
    return {key: selected.get(key, 0.0) for key in domain}
