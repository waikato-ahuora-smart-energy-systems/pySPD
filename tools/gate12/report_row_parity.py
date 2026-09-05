"""Identity-strict row parity for proven Authority/PySPD report mappings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from tools.gate12.bus_price_degeneracy import (
    BusPriceCaseCertificate,
    BusPriceDegeneracyResult,
)
from tools.gate12.energy_allocation import EnergyAllocationCertificate
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.replay_artifacts import CanonicalReplayBundleStore
from tools.gate12.report_crosswalk import (
    REPORT_SCHEMA_CROSSWALK_PROFILE,
    ReportSchemaCrosswalkValidator,
)
from tools.gate12.zero_flow_price_convention import (
    ZeroFlowPriceConventionResult,
)

REPORT_ROW_PARITY_PROFILE = "authority-pyspd-mapped-report-row-parity-v8"
REPORT_ROW_BUS_CERTIFIED_PROFILE = (
    "authority-pyspd-mapped-report-row-parity-bus-certified-v8"
)
REPORT_ROW_ZERO_FLOW_CERTIFIED_PROFILE = (
    "authority-pyspd-mapped-report-row-parity-zero-flow-certified-v8"
)
_LEGACY_REPORT_ROW_PROFILES = frozenset(
    {
        "authority-pyspd-mapped-report-row-parity-v3",
        "authority-pyspd-mapped-report-row-parity-bus-certified-v3",
        "authority-pyspd-mapped-report-row-parity-zero-flow-certified-v3",
        "authority-pyspd-mapped-report-row-parity-v4",
        "authority-pyspd-mapped-report-row-parity-bus-certified-v4",
        "authority-pyspd-mapped-report-row-parity-zero-flow-certified-v4",
        "authority-pyspd-mapped-report-row-parity-v5",
        "authority-pyspd-mapped-report-row-parity-bus-certified-v5",
        "authority-pyspd-mapped-report-row-parity-zero-flow-certified-v5",
        "authority-pyspd-mapped-report-row-parity-v6",
        "authority-pyspd-mapped-report-row-parity-bus-certified-v6",
        "authority-pyspd-mapped-report-row-parity-zero-flow-certified-v6",
        "authority-pyspd-mapped-report-row-parity-v7",
        "authority-pyspd-mapped-report-row-parity-bus-certified-v7",
        "authority-pyspd-mapped-report-row-parity-zero-flow-certified-v7",
    }
)
_MAX_EXAMPLES = 20
_PORTABLE_PRICE_TOLERANCE = Decimal("0.001")
_PORTABLE_PUBLISHED_PRICE_TOLERANCE = Decimal("0.0001")
_PORTABLE_RISK_PRICE_TOLERANCE = Decimal("0.0001")
_PORTABLE_MONEY_TOLERANCE = Decimal("0.01")
_BINARY_FLOAT_RENDERING_SLACK = Decimal("0.000000000001")
_SOLVER_ROUNDING_BOUNDARY_SLACK = Decimal("0.000001")
_RAW_PRICE_OBSERVABLES = frozenset(
    {
        "branch-from-price",
        "branch-to-price",
        "branch-marginal-price",
    }
)
_PUBLISHED_PRICE_OBSERVABLES = frozenset(
    {
        "published-energy-price",
        "published-FIR-price",
        "published-SIR-price",
    }
)
_MARKET_NODE_DUAL_FAMILY_SUFFIXES = ("CTRLMAX", "MW+6", "MW+60")


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _identity(value: str) -> str:
    return value


def _pipe_tail(value: str) -> str:
    return value.rsplit("|", 1)[-1]


@dataclass(frozen=True, slots=True)
class _Projection:
    reference_table: str
    candidate_table: str
    observable: str
    reference_identity: tuple[str, ...]
    candidate_identity: tuple[str, ...]
    reference_value: str
    candidate_value: str
    candidate_filter: tuple[str, str] | None = None
    candidate_filter_prefix: tuple[str, str] | None = None
    candidate_support_fields: tuple[str, ...] = ()
    candidate_value_resolver: Callable[[dict[str, str]], str] | None = None
    candidate_identity_normalizer: Callable[[str], str] = _identity
    candidate_interval: str | None = None


def _projection(
    reference_table: str,
    candidate_table: str,
    observable: str,
    reference_identity: tuple[str, ...],
    candidate_identity: tuple[str, ...],
    reference_value: str,
    candidate_value: str,
    *,
    candidate_filter: tuple[str, str] | None = None,
    candidate_filter_prefix: tuple[str, str] | None = None,
    candidate_support_fields: tuple[str, ...] = (),
    candidate_value_resolver: Callable[[dict[str, str]], str] | None = None,
    candidate_identity_normalizer: Callable[[str], str] = _identity,
    candidate_interval: str | None = None,
) -> _Projection:
    return _Projection(
        reference_table,
        candidate_table,
        observable,
        reference_identity,
        candidate_identity,
        reference_value,
        candidate_value,
        candidate_filter,
        candidate_filter_prefix,
        candidate_support_fields,
        candidate_value_resolver,
        candidate_identity_normalizer,
        candidate_interval,
    )


def _active_bound(row: dict[str, str]) -> str:
    lower = row.get("lower", "")
    upper = row.get("upper", "")
    if lower and upper:
        if Decimal(lower) != Decimal(upper):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: ranged constraint has no single RHS"
            )
        return lower
    if lower:
        return lower
    if upper:
        return upper
    raise EvidenceContractError("REQ-G12-REPORT-ROW: constraint has no finite RHS")


def _constraint_sense(row: dict[str, str]) -> str:
    lower = bool(row.get("lower", ""))
    upper = bool(row.get("upper", ""))
    if lower and upper:
        return "0"
    if lower:
        return "1"
    if upper:
        return "-1"
    raise EvidenceContractError("REQ-G12-REPORT-ROW: constraint has no finite sense")


_CASE_TIME = ("CaseID", "DateTime")
_CASE_TIME_CANDIDATE = ("case_id", "date_time")
_RISK_IDENTITY = (
    *_CASE_TIME,
    "Island",
    "ReserveClass",
    "RiskClass",
    "RiskType",
    "RiskSetter",
)
_RISK_IDENTITY_CANDIDATE = (
    *_CASE_TIME_CANDIDATE,
    "island",
    "reserve_class",
    "risk_class",
    "risk_type",
    "risk_setter",
)
_RISK_VALUES = (
    ("covered-energy", "CoveredEnergy", "covered_energy_mw"),
    ("covered-reserve", "CoveredReserve", "covered_reserve_mw"),
    ("covered-fk-band", "CoveredFKBand", "covered_fk_band_mw"),
    ("risk-subtractor", "RiskSubtractor", "risk_subtractor_mw"),
    ("risk-reserve", "Reserve", "reserve_mw"),
    ("risk-shortfall", "Shortfall", "shortfall_mw"),
    ("risk-deficit", "Deficit", "deficit_mw"),
    ("risk-reserve-price", "ReservePrice", "reserve_price_nzd_per_mwh"),
    ("risk-price", "RiskPrice", "risk_price_nzd_per_mwh"),
)
_SUMMARY_VALUES = (
    ("solve-status", "SolveStatus (1=OK)", "status_code"),
    ("system-ofv", "SystemOFV", "system_ofv_nzd"),
    ("system-cost", "SystemCost", "system_cost_nzd"),
    ("system-benefit", "SystemBenefit", "system_benefit_nzd"),
    ("violation-cost", "ViolationCost", "violation_cost_nzd"),
    ("deficit-generation", "DeficitGenViol (MW)", "deficit_generation_mw"),
    ("surplus-generation", "SurplusGenViol (MW)", "surplus_generation_mw"),
    ("deficit-reserve", "DeficitReserveViol (MW)", "deficit_reserve_mw"),
    (
        "surplus-branch-flow",
        "SurplusBranchFlowViol (MW)",
        "surplus_branch_flow_mw",
    ),
    ("deficit-ramp-rate", "DeficitRampRateViol (MW)", "deficit_ramp_rate_mw"),
    ("surplus-ramp-rate", "SurplusRampRateViol (MW)", "surplus_ramp_rate_mw"),
    (
        "deficit-branch-constraint",
        "DeficitBranchGroupConstraintViol (MW)",
        "deficit_branch_constraint_mw",
    ),
    (
        "surplus-branch-constraint",
        "SurplusBranchGroupConstraintViol (MW)",
        "surplus_branch_constraint_mw",
    ),
    (
        "deficit-market-node-constraint",
        "DeficitMNodeConstraintViol (MW)",
        "deficit_market_node_constraint_mw",
    ),
    (
        "surplus-market-node-constraint",
        "SurplusMNodeConstraintViol (MW)",
        "surplus_market_node_constraint_mw",
    ),
)
_BUS_VALUES = (
    ("bus-generation", "Generation (MW)", "generation_mw"),
    ("bus-load", "Load (MW)", "load_mw"),
    ("bus-deficit", "Deficit(MW)", "deficit_mw"),
    ("bus-surplus", "Surplus(MW)", "surplus_mw"),
)
_NODE_VALUES = (
    ("node-generation", "Generation (MW)", "generation_mw"),
    ("node-load", "Load (MW)", "load_mw"),
    ("node-deficit", "Deficit(MW)", "deficit_mw"),
    ("node-surplus", "Surplus(MW)", "surplus_mw"),
)
_BRANCH_VALUES = (
    ("branch-capacity", "Capacity (MW)", "capacity_mw", None),
    ("branch-dynamic-loss", "DynamicLoss (MW)", "dynamic_loss_mw", None),
    ("branch-fixed-loss", "FixedLoss (MW)", "fixed_loss_mw", None),
    (
        "branch-from-price",
        "FromBusPrice ($/MWh)",
        "from_bus_price_nzd_per_mwh",
        "from_bus_price_interval",
    ),
    (
        "branch-to-price",
        "ToBusPrice ($/MWh)",
        "to_bus_price_nzd_per_mwh",
        "to_bus_price_interval",
    ),
    (
        "branch-marginal-price",
        "BranchPrice ($/MWh)",
        "branch_price_nzd_per_mwh",
        None,
    ),
    ("branch-rentals", "BranchRentals ($)", "branch_rentals_nzd", None),
)
_ISLAND_COMMON_VALUES = (
    ("island-generation", "Gen (MW)", "generation_mw"),
    ("island-load", "Load (MW)", "load_mw"),
    ("island-bid-load", "Bid Load (MW)", "bid_load_mw"),
    ("island-ac-loss", "IslandACLoss (MW)", "ac_loss_mw"),
    ("island-hvdc-flow", "HVDCFlow (MW)", "hvdc_flow_mw"),
    ("island-hvdc-loss", "HVDCLoss (MW)", "hvdc_loss_mw"),
    ("island-reference-price", "ReferencePrice ($/MWh)", "reference_price_nzd_per_mwh"),
)
_PROJECTIONS = (
    _projection(
        "BidResults_TP",
        "bid",
        "cleared-bid-mw",
        (*_CASE_TIME, "Bid", "Trader"),
        (*_CASE_TIME_CANDIDATE, "bid", "trader"),
        "Cleared Bid (MW)",
        "purchase_mw",
    ),
    _projection(
        "BidResults_TP",
        "bid",
        "total-bid-mw",
        (*_CASE_TIME, "Bid", "Trader"),
        (*_CASE_TIME_CANDIDATE, "bid", "trader"),
        "Total Bid (MW)",
        "total_bid_mw",
    ),
    _projection(
        "BrConstraintResults_TP",
        "constraint",
        "branch-constraint-lhs",
        (*_CASE_TIME, "BranchConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "LHS (MW)",
        "body",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.BranchSecurityConstraint",
        ),
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BrConstraintResults_TP",
        "constraint",
        "branch-constraint-rhs",
        (*_CASE_TIME, "BranchConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "RHS (MW)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.BranchSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_active_bound,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BrConstraintResults_TP",
        "constraint",
        "branch-constraint-sense",
        (*_CASE_TIME, "BranchConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "Sense (-1:<=, 0:=, 1:>=)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.BranchSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_constraint_sense,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BranchResults_TP",
        "branch",
        "branch-flow-mw",
        (*_CASE_TIME, "Branch", "FromBus", "ToBus"),
        (*_CASE_TIME_CANDIDATE, "branch", "from_bus", "to_bus"),
        "Flow (MW) (From->To)",
        "flow_mw",
        candidate_identity_normalizer=_pipe_tail,
    ),
    *(
        _projection(
            "BranchResults_TP",
            "branch",
            observable,
            (*_CASE_TIME, "Branch", "FromBus", "ToBus"),
            (*_CASE_TIME_CANDIDATE, "branch", "from_bus", "to_bus"),
            reference_value,
            candidate_value,
            candidate_identity_normalizer=_pipe_tail,
            candidate_interval=candidate_interval,
        )
        for observable, reference_value, candidate_value, candidate_interval in _BRANCH_VALUES
    ),
    _projection(
        "BusResults_TP",
        "bus",
        "repaired-bus-price",
        (*_CASE_TIME, "Bus"),
        (*_CASE_TIME_CANDIDATE, "bus"),
        "Price ($/MWh)",
        "repaired_price_nzd_per_mwh",
        candidate_interval="price_interval",
    ),
    *(
        _projection(
            "BusResults_TP",
            "bus",
            observable,
            (*_CASE_TIME, "Bus"),
            (*_CASE_TIME_CANDIDATE, "bus"),
            reference_value,
            candidate_value,
        )
        for observable, reference_value, candidate_value in _BUS_VALUES
    ),
    _projection(
        "IslandResults_TP",
        "island",
        "FIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "FIR Price ($/MWh)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "FIR"),
        candidate_interval="price_interval",
    ),
    _projection(
        "IslandResults_TP",
        "island",
        "SIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "SIR Price ($/MWh)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "SIR"),
        candidate_interval="price_interval",
    ),
    *(
        _projection(
            "IslandResults_TP",
            "island",
            observable,
            (*_CASE_TIME, "Island"),
            (*_CASE_TIME_CANDIDATE, "island"),
            reference_value,
            candidate_value,
            candidate_filter=("reserve_class", "FIR"),
        )
        for observable, reference_value, candidate_value in _ISLAND_COMMON_VALUES
    ),
    *(
        _projection(
            "IslandResults_TP",
            "island",
            f"{reserve_class}-{observable}",
            (*_CASE_TIME, "Island"),
            (*_CASE_TIME_CANDIDATE, "island"),
            reference_value,
            candidate_value,
            candidate_filter=("reserve_class", reserve_class),
        )
        for reserve_class, values in (
            (
                "FIR",
                (
                    ("required", "FIR_req (MW)", "required_mw"),
                    ("cleared", "FIR_Clear", "cleared_mw"),
                    ("shared", "FIR_Share", "share_mw"),
                    ("received", "FIR_Receive", "received_mw"),
                    ("effective-ce", "FIR_Effective_CE", "effective_ce_mw"),
                    ("effective-ece", "FIR_Effective_ECE", "effective_ece_mw"),
                ),
            ),
            (
                "SIR",
                (
                    ("required", "SIR_req (MW)", "required_mw"),
                    ("cleared", "SIR_Clear", "cleared_mw"),
                    ("shared", "SIR_Share", "share_mw"),
                    ("received", "SIR_Receive", "received_mw"),
                    ("effective-ce", "SIR_Effective_CE", "effective_ce_mw"),
                    ("effective-ece", "SIR_Effective_ECE", "effective_ece_mw"),
                ),
            ),
        )
        for observable, reference_value, candidate_value in values
    ),
    _projection(
        "MNodeConstraintResults_TP",
        "constraint",
        "market-node-constraint-lhs",
        (*_CASE_TIME, "MNodeConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "LHS (MW)",
        "body",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.MNodeSecurityConstraint",
        ),
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "MNodeConstraintResults_TP",
        "constraint",
        "market-node-constraint-price",
        (*_CASE_TIME, "MNodeConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "Price ($/MWh)",
        "price_nzd_per_mwh",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.MNodeSecurityConstraint",
        ),
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "BrConstraintResults_TP",
        "constraint",
        "branch-constraint-price",
        (*_CASE_TIME, "BranchConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "Price ($/MWh)",
        "price_nzd_per_mwh",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.BranchSecurityConstraint",
        ),
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "MNodeConstraintResults_TP",
        "constraint",
        "market-node-constraint-rhs",
        (*_CASE_TIME, "MNodeConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "RHS (MW)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.MNodeSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_active_bound,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "MNodeConstraintResults_TP",
        "constraint",
        "market-node-constraint-sense",
        (*_CASE_TIME, "MNodeConstraint"),
        (*_CASE_TIME_CANDIDATE, "index"),
        "Sense (-1:<=, 0:=, 1:>=)",
        "lower",
        candidate_filter_prefix=(
            "constraint",
            "NetworkSecurity.MNodeSecurityConstraint",
        ),
        candidate_support_fields=("upper",),
        candidate_value_resolver=_constraint_sense,
        candidate_identity_normalizer=_pipe_tail,
    ),
    _projection(
        "NodeResults_TP",
        "node",
        "node-price",
        (*_CASE_TIME, "Node"),
        (*_CASE_TIME_CANDIDATE, "node"),
        "Price ($/MWh)",
        "price_nzd_per_mwh",
        candidate_interval="price_interval",
    ),
    *(
        _projection(
            "NodeResults_TP",
            "node",
            observable,
            (*_CASE_TIME, "Node"),
            (*_CASE_TIME_CANDIDATE, "node"),
            reference_value,
            candidate_value,
        )
        for observable, reference_value, candidate_value in _NODE_VALUES
    ),
    _projection(
        "OfferResults_TP",
        "offer",
        "generation-mw",
        (*_CASE_TIME, "Offer", "Trader"),
        (*_CASE_TIME_CANDIDATE, "offer", "trader"),
        "Generation (MW)",
        "generation_mw",
    ),
    *(
        _projection(
            "OfferResults_TP",
            "offer",
            f"offer-{reserve_class}",
            (*_CASE_TIME, "Offer", "Trader"),
            (*_CASE_TIME_CANDIDATE, "offer", "trader"),
            f"{reserve_class} (MW)",
            f"{reserve_class.lower()}_mw",
        )
        for reserve_class in ("FIR", "SIR")
    ),
    _projection(
        "PublishedEnergyPrices_TP",
        "published_price",
        "published-energy-price",
        ("DateTime", "TradingPeriod", "Pnodename"),
        ("date_time", "trading_period", "location"),
        "vSPDDollarsPerMegawattHour",
        "price_nzd_per_mwh",
        candidate_filter=("product", "energy"),
        candidate_interval="price_interval",
    ),
    _projection(
        "PublishedReservePrices_TP",
        "published_price",
        "published-FIR-price",
        ("DateTime", "TradingPeriod", "Island"),
        ("date_time", "trading_period", "location"),
        "vSPDFIRDollarsPerMegawattHour",
        "price_nzd_per_mwh",
        candidate_filter=("product", "FIR"),
        candidate_interval="price_interval",
    ),
    _projection(
        "PublishedReservePrices_TP",
        "published_price",
        "published-SIR-price",
        ("DateTime", "TradingPeriod", "Island"),
        ("date_time", "trading_period", "location"),
        "vSPDSIRDollarsPerMegawattHour",
        "price_nzd_per_mwh",
        candidate_filter=("product", "SIR"),
        candidate_interval="price_interval",
    ),
    _projection(
        "ReserveResults_TP",
        "reserve",
        "FIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "FIR Price ($/MW)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "FIR"),
        candidate_interval="price_interval",
    ),
    _projection(
        "ReserveResults_TP",
        "reserve",
        "SIR-price",
        (*_CASE_TIME, "Island"),
        (*_CASE_TIME_CANDIDATE, "island"),
        "SIR Price ($/MW)",
        "price_nzd_per_mwh",
        candidate_filter=("reserve_class", "SIR"),
        candidate_interval="price_interval",
    ),
    *(
        _projection(
            "ReserveResults_TP",
            "reserve",
            f"{reserve_class}-{observable}",
            (*_CASE_TIME, "Island"),
            (*_CASE_TIME_CANDIDATE, "island"),
            reference_value,
            candidate_value,
            candidate_filter=("reserve_class", reserve_class),
        )
        for reserve_class, values in (
            (
                "FIR",
                (
                    ("required", "FIR Reqd (MW)", "required_mw"),
                    ("violation", "FIR Violation (MW)", "violation_mw"),
                ),
            ),
            (
                "SIR",
                (
                    ("required", "SIR Reqd (MW)", "required_mw"),
                    ("violation", "SIR Violation (MW)", "violation_mw"),
                ),
            ),
        )
        for observable, reference_value, candidate_value in values
    ),
    *(
        _projection(
            "RiskResults_TP",
            "risk",
            observable,
            _RISK_IDENTITY,
            _RISK_IDENTITY_CANDIDATE,
            reference_value,
            candidate_value,
        )
        for observable, reference_value, candidate_value in _RISK_VALUES
    ),
    *(
        _projection(
            "SummaryResults_TP",
            "summary",
            observable,
            _CASE_TIME,
            _CASE_TIME_CANDIDATE,
            reference_value,
            candidate_value,
        )
        for observable, reference_value, candidate_value in _SUMMARY_VALUES
    ),
)


@dataclass(frozen=True, slots=True)
class ReportValueDifference:
    observable: str
    identity: tuple[str, ...]
    reference_value: str
    candidate_value: str
    absolute_error: str
    authority_half_unit: str

    def to_dict(self) -> dict[str, object]:
        return {
            "observable": self.observable,
            "identity": list(self.identity),
            "reference_value": self.reference_value,
            "candidate_value": self.candidate_value,
            "absolute_error": self.absolute_error,
            "authority_half_unit": self.authority_half_unit,
        }


@dataclass(frozen=True, slots=True)
class ReportRowTableResult:
    reference_table: str
    candidate_table: str
    observables: tuple[str, ...]
    compared_value_count: int
    missing_identity_count: int
    extra_identity_count: int
    certified_difference_count: int
    above_precision_count: int
    maximum_absolute_error: str
    maximum_difference: ReportValueDifference | None
    missing_identity_examples: tuple[tuple[str, ...], ...]
    extra_identity_examples: tuple[tuple[str, ...], ...]
    differences: tuple[ReportValueDifference, ...]

    @property
    def passed(self) -> bool:
        return (
            self.missing_identity_count == 0
            and self.extra_identity_count == 0
            and self.above_precision_count == 0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_table": self.reference_table,
            "candidate_table": self.candidate_table,
            "observables": list(self.observables),
            "passed": self.passed,
            "compared_value_count": self.compared_value_count,
            "missing_identity_count": self.missing_identity_count,
            "extra_identity_count": self.extra_identity_count,
            "certified_difference_count": self.certified_difference_count,
            "above_precision_count": self.above_precision_count,
            "maximum_absolute_error": self.maximum_absolute_error,
            "maximum_difference": (
                self.maximum_difference.to_dict()
                if self.maximum_difference is not None
                else None
            ),
            "missing_identity_examples": [
                list(identity) for identity in self.missing_identity_examples
            ],
            "extra_identity_examples": [
                list(identity) for identity in self.extra_identity_examples
            ],
            "differences": [item.to_dict() for item in self.differences],
        }


@dataclass(frozen=True, slots=True)
class ReportCaseRowParity:
    case_id: str
    reference_report_sha256: str
    candidate_report_sha256: str
    tables: tuple[ReportRowTableResult, ...]
    unimplemented_reference_tables: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return bool(
            self.tables
            and all(table.passed for table in self.tables)
            and not self.unimplemented_reference_tables
        )

    @property
    def missing_identity_count(self) -> int:
        return sum(table.missing_identity_count for table in self.tables)

    @property
    def extra_identity_count(self) -> int:
        return sum(table.extra_identity_count for table in self.tables)

    @property
    def above_precision_count(self) -> int:
        return sum(table.above_precision_count for table in self.tables)

    @property
    def certified_difference_count(self) -> int:
        return sum(table.certified_difference_count for table in self.tables)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "reference_report_sha256": self.reference_report_sha256,
            "candidate_report_sha256": self.candidate_report_sha256,
            "missing_identity_count": self.missing_identity_count,
            "extra_identity_count": self.extra_identity_count,
            "certified_difference_count": self.certified_difference_count,
            "above_precision_count": self.above_precision_count,
            "unimplemented_reference_tables": list(self.unimplemented_reference_tables),
            "tables": [table.to_dict() for table in self.tables],
        }


class ReportRowParityValidator:
    """Project only fields admitted by the schema crosswalk and compare rows."""

    def compare(
        self,
        *,
        case_id: str,
        reference: bytes,
        candidate: bytes,
        bus_price_certificate: BusPriceCaseCertificate | None = None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None = None,
        energy_allocation_certificate: EnergyAllocationCertificate | None = None,
    ) -> ReportCaseRowParity:
        if bus_price_certificate is not None and (
            not bus_price_certificate.passed or bus_price_certificate.case_id != case_id
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: invalid case bus-price certificate"
            )
        if (
            zero_flow_price_certificate is not None
            and not zero_flow_price_certificate.passed
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: invalid zero-flow price certificate"
            )
        if energy_allocation_certificate is not None:
            energy_allocation_certificate.validate()
        schema = ReportSchemaCrosswalkValidator().compare(
            case_id=case_id, reference=reference, candidate=candidate
        )
        reference_payload = self._payload(reference, "reference")
        candidate_payload = self._payload(candidate, "candidate")
        reference_tables = self._reference_tables(reference_payload)
        mapping_by_table = {
            table.reference_table: {
                mapping.reference_field: mapping for mapping in table.field_mappings
            }
            for table in schema.tables
        }
        results = []
        implemented: set[str] = set()
        for reference_table in sorted(reference_tables):
            projections = tuple(
                item
                for item in _PROJECTIONS
                if item.reference_table == reference_table
                and self._admitted(item, mapping_by_table.get(reference_table, {}))
            )
            if not projections:
                continue
            implemented.add(reference_table)
            results.append(
                self._compare_table(
                    projections,
                    reference_tables[reference_table],
                    candidate_payload.get(projections[0].candidate_table),
                    bus_price_certificate,
                    zero_flow_price_certificate,
                    energy_allocation_certificate,
                )
            )
        return ReportCaseRowParity(
            case_id=case_id,
            reference_report_sha256=hashlib.sha256(reference).hexdigest(),
            candidate_report_sha256=hashlib.sha256(candidate).hexdigest(),
            tables=tuple(results),
            unimplemented_reference_tables=tuple(
                sorted(set(reference_tables) - implemented)
            ),
        )

    @staticmethod
    def _admitted(projection: _Projection, mappings: dict[str, Any]) -> bool:
        value_mapping = mappings.get(projection.reference_value)
        required_value_fields = {
            projection.candidate_value,
            *projection.candidate_support_fields,
        }
        if value_mapping is None or not required_value_fields.issubset(
            value_mapping.candidate_fields
        ):
            return False
        for reference_field, candidate_field in zip(
            projection.reference_identity, projection.candidate_identity, strict=True
        ):
            identity_mapping = mappings.get(reference_field)
            if (
                identity_mapping is None
                or candidate_field not in identity_mapping.candidate_fields
            ):
                return False
        return True

    def _compare_table(
        self,
        projections: tuple[_Projection, ...],
        reference_table: dict[str, Any],
        candidate_table: object,
        bus_price_certificate: BusPriceCaseCertificate | None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None,
        energy_allocation_certificate: EnergyAllocationCertificate | None,
    ) -> ReportRowTableResult:
        candidate_name = projections[0].candidate_table
        reference_rows = self._rows(reference_table, "reference")
        candidate_rows = self._rows(candidate_table, "candidate")
        compared = missing = extra = certified = above = 0
        maximum = Decimal(0)
        maximum_difference: ReportValueDifference | None = None
        missing_examples: list[tuple[str, ...]] = []
        extra_examples: list[tuple[str, ...]] = []
        differences: list[ReportValueDifference] = []
        for projection in projections:
            expected = self._indexed_values(reference_rows, projection, reference=True)
            actual = self._indexed_values(candidate_rows, projection, reference=False)
            candidate_intervals = self._indexed_intervals(
                candidate_rows, projection
            )
            missing_keys = sorted(set(expected) - set(actual))
            extra_keys = sorted(set(actual) - set(expected))
            missing += len(missing_keys)
            extra += len(extra_keys)
            missing_examples.extend(
                missing_keys[: max(0, _MAX_EXAMPLES - len(missing_examples))]
            )
            extra_examples.extend(
                extra_keys[: max(0, _MAX_EXAMPLES - len(extra_examples))]
            )
            allocation_equivalent = self._offer_allocation_equivalent(
                projection, expected, actual
            )
            market_node_dual_equivalent = (
                self._binding_market_node_dual_allocation_keys(
                    projection,
                    expected,
                    actual,
                    reference_rows,
                    candidate_rows,
                )
            )
            nonbinding_market_node_activity = (
                self._nonbinding_market_node_activity_keys(
                    projection,
                    expected,
                    actual,
                    reference_rows,
                    candidate_rows,
                )
            )
            for key in sorted(set(expected) & set(actual)):
                reference_text = expected[key]
                candidate_text = actual[key]
                reference_value = self._decimal(reference_text)
                candidate_value = self._decimal(candidate_text)
                absolute_error = abs(reference_value - candidate_value)
                exponent = cast(int, reference_value.as_tuple().exponent)
                half_unit = Decimal(5).scaleb(exponent - 1)
                tolerance = self._acceptance_tolerance(projection.observable, half_unit)
                if absolute_error > maximum:
                    maximum = absolute_error
                    maximum_difference = ReportValueDifference(
                        projection.observable,
                        key,
                        reference_text,
                        candidate_text,
                        format(absolute_error, "f"),
                        format(tolerance, "f"),
                    )
                compared += 1
                if absolute_error <= tolerance + _BINARY_FLOAT_RENDERING_SLACK:
                    if absolute_error > half_unit + _BINARY_FLOAT_RENDERING_SLACK:
                        certified += 1
                    continue
                if allocation_equivalent:
                    certified += 1
                    continue
                if (
                    energy_allocation_certificate is not None
                    and energy_allocation_certificate.certifies(key)
                ):
                    certified += 1
                    continue
                interval = candidate_intervals.get(key)
                if interval is not None and (
                    interval[0] - tolerance
                    <= reference_value
                    <= interval[1] + tolerance
                ):
                    certified += 1
                    continue
                if key in market_node_dual_equivalent:
                    certified += 1
                    continue
                if key in nonbinding_market_node_activity:
                    certified += 1
                    continue
                if (
                    projection.reference_table == "BusResults_TP"
                    and projection.observable == "repaired-bus-price"
                    and bus_price_certificate is not None
                ):
                    certified += 1
                    continue
                if (
                    zero_flow_price_certificate is not None
                    and self._zero_flow_certifies_report_value(
                        zero_flow_price_certificate,
                        projection.observable,
                        key,
                    )
                ):
                    certified += 1
                    continue
                above += 1
                if len(differences) < _MAX_EXAMPLES:
                    differences.append(
                        ReportValueDifference(
                            projection.observable,
                            key,
                            reference_text,
                            candidate_text,
                            format(absolute_error, "f"),
                            format(tolerance, "f"),
                        )
                    )
        return ReportRowTableResult(
            reference_table=projections[0].reference_table,
            candidate_table=candidate_name,
            observables=tuple(item.observable for item in projections),
            compared_value_count=compared,
            missing_identity_count=missing,
            extra_identity_count=extra,
            certified_difference_count=certified,
            above_precision_count=above,
            maximum_absolute_error=format(maximum, "f"),
            maximum_difference=maximum_difference,
            missing_identity_examples=tuple(missing_examples),
            extra_identity_examples=tuple(extra_examples),
            differences=tuple(differences),
        )

    @staticmethod
    def _acceptance_tolerance(observable: str, display_half_unit: Decimal) -> Decimal:
        if observable in _RAW_PRICE_OBSERVABLES:
            return max(display_half_unit, _PORTABLE_PRICE_TOLERANCE)
        if observable in _PUBLISHED_PRICE_OBSERVABLES:
            return max(display_half_unit, _PORTABLE_PUBLISHED_PRICE_TOLERANCE)
        if observable == "risk-price":
            return max(display_half_unit, _PORTABLE_RISK_PRICE_TOLERANCE)
        if observable == "branch-rentals":
            return max(display_half_unit, _PORTABLE_MONEY_TOLERANCE)
        if observable == "repaired-bus-price":
            return display_half_unit + _SOLVER_ROUNDING_BOUNDARY_SLACK
        return display_half_unit

    @staticmethod
    def _offer_allocation_equivalent(
        projection: _Projection,
        expected: dict[tuple[str, ...], str],
        actual: dict[tuple[str, ...], str],
    ) -> bool:
        if projection.observable not in {"offer-FIR", "offer-SIR"}:
            return False
        if not expected or set(expected) != set(actual):
            return False
        expected_values = [
            ReportRowParityValidator._decimal(value) for value in expected.values()
        ]
        actual_values = [
            ReportRowParityValidator._decimal(value) for value in actual.values()
        ]
        if any(value < 0 for value in (*expected_values, *actual_values)):
            return False
        rounding_budget = sum(
            (
                Decimal(5).scaleb(cast(int, value.as_tuple().exponent) - 1)
                for value in expected_values
            ),
            start=Decimal(0),
        )
        expected_total = sum(expected_values, start=Decimal(0))
        actual_total = sum(actual_values, start=Decimal(0))
        return abs(expected_total - actual_total) <= rounding_budget

    def _binding_market_node_dual_allocation_keys(
        self,
        projection: _Projection,
        expected: dict[tuple[str, ...], str],
        actual: dict[tuple[str, ...], str],
        reference_rows: tuple[dict[str, str], ...],
        candidate_rows: tuple[dict[str, str], ...],
    ) -> frozenset[tuple[str, ...]]:
        """Certify solver-dependent dual placement across one binding limit family.

        vSPD inputs can contain a control maximum and reserve-inclusive variants
        for the same offer.  When reserve is zero, several rows are simultaneously
        binding and an LP solver may place their common shadow-price total on a
        different row.  Admission is deliberately narrow: the governed names,
        identities, senses, binding status, non-negative duals, and aggregate dual
        must all agree.
        """

        if (
            projection.observable != "market-node-constraint-price"
            or not expected
            or set(expected) != set(actual)
        ):
            return frozenset()
        related = {
            item.observable: item
            for item in _PROJECTIONS
            if item.reference_table == "MNodeConstraintResults_TP"
            and item.observable
            in {
                "market-node-constraint-lhs",
                "market-node-constraint-rhs",
                "market-node-constraint-sense",
            }
        }
        if len(related) != 3:
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: market-node support projections are incomplete"
            )
        support: dict[
            str, tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], str]]
        ] = {}
        for observable, item in related.items():
            support[observable] = (
                self._indexed_values(reference_rows, item, reference=True),
                self._indexed_values(candidate_rows, item, reference=False),
            )

        grouped: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
        for key in expected:
            if len(key) < 4:
                continue
            constraint = key[-2]
            base = self._market_node_dual_family_base(constraint)
            if base is not None:
                grouped.setdefault((*key[:-2], base), []).append(key)

        certified: set[tuple[str, ...]] = set()
        for keys in grouped.values():
            if len(keys) < 2:
                continue
            reference_prices = [self._decimal(expected[key]) for key in keys]
            candidate_prices = [self._decimal(actual[key]) for key in keys]
            if any(value < 0 for value in reference_prices + candidate_prices):
                continue
            rounding_budget = sum(
                (
                    Decimal(5).scaleb(cast(int, value.as_tuple().exponent) - 1)
                    for value in reference_prices
                ),
                start=Decimal(0),
            )
            reference_total = sum(reference_prices, start=Decimal(0))
            candidate_total = sum(candidate_prices, start=Decimal(0))
            if abs(reference_total - candidate_total) > rounding_budget:
                continue
            if not all(self._market_node_row_is_binding(key, support) for key in keys):
                continue
            certified.update(keys)
        return frozenset(certified)

    def _nonbinding_market_node_activity_keys(
        self,
        projection: _Projection,
        expected: dict[tuple[str, ...], str],
        actual: dict[tuple[str, ...], str],
        reference_rows: tuple[dict[str, str], ...],
        candidate_rows: tuple[dict[str, str], ...],
    ) -> frozenset[tuple[str, ...]]:
        """Certify alternate-optimum activity on mutually slack zero-dual rows."""

        if (
            projection.observable != "market-node-constraint-lhs"
            or not expected
            or set(expected) != set(actual)
        ):
            return frozenset()
        related = {
            item.observable: item
            for item in _PROJECTIONS
            if item.reference_table == "MNodeConstraintResults_TP"
            and item.observable
            in {
                "market-node-constraint-price",
                "market-node-constraint-rhs",
                "market-node-constraint-sense",
            }
        }
        if len(related) != 3:
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: market-node support projections are incomplete"
            )
        support = {
            observable: (
                self._indexed_values(reference_rows, item, reference=True),
                self._indexed_values(candidate_rows, item, reference=False),
            )
            for observable, item in related.items()
        }
        certified: set[tuple[str, ...]] = set()
        for lhs_key, ref_lhs_text in expected.items():
            keys = {name: (*lhs_key[:-1], name) for name in related}
            if not all(
                key in values for name, key in keys.items() for values in support[name]
            ):
                continue
            ref_price = self._decimal(
                support["market-node-constraint-price"][0][
                    keys["market-node-constraint-price"]
                ]
            )
            cand_price = self._decimal(
                support["market-node-constraint-price"][1][
                    keys["market-node-constraint-price"]
                ]
            )
            ref_rhs = self._decimal(
                support["market-node-constraint-rhs"][0][
                    keys["market-node-constraint-rhs"]
                ]
            )
            cand_rhs = self._decimal(
                support["market-node-constraint-rhs"][1][
                    keys["market-node-constraint-rhs"]
                ]
            )
            ref_sense = self._decimal(
                support["market-node-constraint-sense"][0][
                    keys["market-node-constraint-sense"]
                ]
            )
            cand_sense = self._decimal(
                support["market-node-constraint-sense"][1][
                    keys["market-node-constraint-sense"]
                ]
            )
            ref_lhs = self._decimal(ref_lhs_text)
            cand_lhs = self._decimal(actual[lhs_key])
            ref_rhs_half_unit = Decimal(5).scaleb(
                cast(int, ref_rhs.as_tuple().exponent) - 1
            )
            ref_price_half_unit = Decimal(5).scaleb(
                cast(int, ref_price.as_tuple().exponent) - 1
            )
            same_limit = abs(ref_rhs - cand_rhs) <= ref_rhs_half_unit
            zero_dual = (
                abs(ref_price) <= ref_price_half_unit
                and abs(cand_price) <= ref_price_half_unit
            )
            mutually_slack = (
                ref_sense == cand_sense == Decimal(-1)
                and ref_rhs - ref_lhs > ref_rhs_half_unit
                and cand_rhs - cand_lhs > ref_rhs_half_unit
            ) or (
                ref_sense == cand_sense == Decimal(1)
                and ref_lhs - ref_rhs > ref_rhs_half_unit
                and cand_lhs - cand_rhs > ref_rhs_half_unit
            )
            if same_limit and zero_dual and mutually_slack:
                certified.add(lhs_key)
        return frozenset(certified)

    @staticmethod
    def _market_node_dual_family_base(constraint: str) -> str | None:
        for suffix in _MARKET_NODE_DUAL_FAMILY_SUFFIXES:
            marker = f"_{suffix}"
            if constraint.endswith(marker):
                return constraint[: -len(marker)]
        return None

    def _market_node_row_is_binding(
        self,
        price_key: tuple[str, ...],
        support: dict[
            str,
            tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], str]],
        ],
    ) -> bool:
        def key(observable: str) -> tuple[str, ...]:
            return (*price_key[:-1], observable)

        lhs = support["market-node-constraint-lhs"]
        rhs = support["market-node-constraint-rhs"]
        sense = support["market-node-constraint-sense"]
        identity_lhs = key("market-node-constraint-lhs")
        identity_rhs = key("market-node-constraint-rhs")
        identity_sense = key("market-node-constraint-sense")
        if not all(
            identity in values
            for identity, values in (
                (identity_lhs, lhs[0]),
                (identity_lhs, lhs[1]),
                (identity_rhs, rhs[0]),
                (identity_rhs, rhs[1]),
                (identity_sense, sense[0]),
                (identity_sense, sense[1]),
            )
        ):
            return False
        reference_rhs = self._decimal(rhs[0][identity_rhs])
        exponent = cast(int, reference_rhs.as_tuple().exponent)
        binding_tolerance = Decimal(5).scaleb(exponent - 1)
        return (
            self._decimal(sense[0][identity_sense]) == Decimal(-1)
            and self._decimal(sense[1][identity_sense]) == Decimal(-1)
            and abs(self._decimal(lhs[0][identity_lhs]) - reference_rhs)
            <= binding_tolerance
            and abs(
                self._decimal(lhs[1][identity_lhs])
                - self._decimal(rhs[1][identity_rhs])
            )
            <= binding_tolerance
        )

    @staticmethod
    def _zero_flow_certifies_report_value(
        certificate: ZeroFlowPriceConventionResult,
        observable: str,
        identity: tuple[str, ...],
    ) -> bool:
        if observable == "repaired-bus-price" and len(identity) >= 3:
            return certificate.certifies_bus(identity[0], identity[2])
        if observable == "node-price" and len(identity) >= 3:
            return certificate.certifies_node(identity[0], identity[2])
        if observable == "branch-from-price" and len(identity) >= 5:
            return certificate.certifies_bus(identity[0], identity[3])
        if observable == "branch-to-price" and len(identity) >= 5:
            return certificate.certifies_bus(identity[0], identity[4])
        if observable == "published-energy-price" and len(identity) >= 3:
            return certificate.certifies_publication(identity[1], identity[2])
        return False

    def _indexed_values(
        self,
        rows: tuple[dict[str, str], ...],
        projection: _Projection,
        *,
        reference: bool,
    ) -> dict[tuple[str, ...], str]:
        fields = (
            projection.reference_identity
            if reference
            else projection.candidate_identity
        )
        value_field = (
            projection.reference_value if reference else projection.candidate_value
        )
        indexed: dict[tuple[str, ...], str] = {}
        for row in rows:
            if not reference and projection.candidate_filter is not None:
                filter_field, filter_value = projection.candidate_filter
                if row.get(filter_field) != filter_value:
                    continue
            if not reference and projection.candidate_filter_prefix is not None:
                filter_field, filter_prefix = projection.candidate_filter_prefix
                if not row.get(filter_field, "").startswith(filter_prefix):
                    continue
            try:
                identity = tuple(row[field] for field in fields)
                value = (
                    projection.candidate_value_resolver(row)
                    if not reference and projection.candidate_value_resolver is not None
                    else row[value_field]
                )
            except KeyError as error:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: projected row field is unavailable"
                ) from error
            if not reference:
                identity = (
                    *identity[:-1],
                    projection.candidate_identity_normalizer(identity[-1]),
                )
            key = (*identity, projection.observable)
            if key in indexed:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: duplicate projected row identity"
                )
            indexed[key] = value
        return indexed

    def _indexed_intervals(
        self,
        rows: tuple[dict[str, str], ...],
        projection: _Projection,
    ) -> dict[tuple[str, ...], tuple[Decimal, Decimal]]:
        if projection.candidate_interval is None:
            return {}
        indexed: dict[tuple[str, ...], tuple[Decimal, Decimal]] = {}
        for row in rows:
            if projection.candidate_filter is not None:
                filter_field, filter_value = projection.candidate_filter
                if row.get(filter_field) != filter_value:
                    continue
            if projection.candidate_filter_prefix is not None:
                filter_field, filter_prefix = projection.candidate_filter_prefix
                if not row.get(filter_field, "").startswith(filter_prefix):
                    continue
            raw = row.get(projection.candidate_interval, "")
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as error:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: projected interval is invalid JSON"
                ) from error
            if not isinstance(parsed, list) or len(parsed) != 2:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: projected interval must contain two bounds"
                )
            lower = self._decimal(str(parsed[0]))
            upper = self._decimal(str(parsed[1]))
            if lower > upper:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: projected interval bounds are reversed"
                )
            try:
                identity = tuple(row[field] for field in projection.candidate_identity)
            except KeyError as error:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: projected interval identity is unavailable"
                ) from error
            identity = (
                *identity[:-1],
                projection.candidate_identity_normalizer(identity[-1]),
            )
            key = (*identity, projection.observable)
            if key in indexed:
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: duplicate projected interval identity"
                )
            indexed[key] = (lower, upper)
        return indexed

    @staticmethod
    def _decimal(value: str) -> Decimal:
        try:
            parsed = Decimal(value)
        except InvalidOperation as error:
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: projected value is not numeric"
            ) from error
        if not parsed.is_finite():
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: projected value is not finite"
            )
        return parsed

    @staticmethod
    def _payload(raw: bytes, role: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                f"REQ-G12-REPORT-ROW: invalid {role} report JSON"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError(
                f"REQ-G12-REPORT-ROW: {role} report must be an object"
            )
        return payload

    @staticmethod
    def _reference_tables(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        supported_names = {item.reference_table for item in _PROJECTIONS}
        supported_names.update(
            {
                "BrConstraintResults_TP",
                "MNodeConstraintResults_TP",
                "RiskResults_TP",
            }
        )
        output: dict[str, dict[str, Any]] = {}
        for raw_name, table in payload.items():
            matches = [
                name
                for name in supported_names
                if raw_name == name or raw_name.endswith(f"_{name}")
            ]
            if len(matches) != 1 or not isinstance(table, dict):
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: invalid reference table"
                )
            output[matches[0]] = table
        return output

    @staticmethod
    def _rows(table: object, role: str) -> tuple[dict[str, str], ...]:
        if table is None:
            return ()
        if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
            raise EvidenceContractError(
                f"REQ-G12-REPORT-ROW: malformed {role} table rows"
            )
        rows = table["rows"]
        if any(
            not isinstance(row, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in row.items()
            )
            for row in rows
        ):
            raise EvidenceContractError(f"REQ-G12-REPORT-ROW: invalid {role} row")
        return tuple(rows)


@dataclass(frozen=True, slots=True)
class ReportRowParityResult:
    profile: str
    trading_date: str
    source_sha256: str
    work_item_sha256: str
    reference_bundle_sha256: str
    candidate_bundle_sha256: str
    schema_crosswalk_sha256: str
    bus_price_certificate_sha256: str | None
    zero_flow_price_certificate_sha256: str | None
    cases: tuple[ReportCaseRowParity, ...]
    logical_sha256: str

    @property
    def passed(self) -> bool:
        return bool(self.cases and all(case.passed for case in self.cases))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": self.profile,
            "scope": "mapped-fields-at-governed-portable-profile-precision",
            "trading_date": self.trading_date,
            "source_sha256": self.source_sha256,
            "work_item_sha256": self.work_item_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "schema_crosswalk_sha256": self.schema_crosswalk_sha256,
            "bus_price_certificate_sha256": self.bus_price_certificate_sha256,
            "zero_flow_price_certificate_sha256": (
                self.zero_flow_price_certificate_sha256
            ),
            "passed": self.passed,
            "missing_identity_count": sum(
                case.missing_identity_count for case in self.cases
            ),
            "extra_identity_count": sum(
                case.extra_identity_count for case in self.cases
            ),
            "certified_difference_count": sum(
                case.certified_difference_count for case in self.cases
            ),
            "above_precision_count": sum(
                case.above_precision_count for case in self.cases
            ),
            "unimplemented_table_count": sum(
                len(case.unimplemented_reference_tables) for case in self.cases
            ),
            "cases": [case.to_dict() for case in self.cases],
        }
        if include_hash:
            payload["logical_sha256"] = self.logical_sha256
        return payload


class ReportRowParityRunner:
    """Compare mapped rows after verifying the exact schema-crosswalk artifact."""

    def __init__(
        self,
        *,
        reference_root: Path,
        candidate_root: Path,
        schema_crosswalk: Path,
        bus_price_certificate: BusPriceDegeneracyResult | None = None,
        zero_flow_price_certificate: ZeroFlowPriceConventionResult | None = None,
    ) -> None:
        self.reference_store = CanonicalReplayBundleStore(reference_root)
        self.candidate_store = CanonicalReplayBundleStore(candidate_root)
        self.schema_payload, self.schema_sha256 = self._load_crosswalk(schema_crosswalk)
        self.bus_price_certificate = bus_price_certificate
        self.zero_flow_price_certificate = zero_flow_price_certificate
        self.validator = ReportRowParityValidator()

    def compare(self, trading_date: str) -> ReportRowParityResult:
        reference, reference_cases = self.reference_store.load(trading_date)
        candidate, candidate_cases = self.candidate_store.load(trading_date)
        if (
            reference.source_sha256 != candidate.source_sha256
            or reference.work_item_sha256 != candidate.work_item_sha256
            or reference.affected_case_ids != candidate.affected_case_ids
            or self.schema_payload.get("trading_date") != trading_date
            or self.schema_payload.get("source_sha256") != reference.source_sha256
            or self.schema_payload.get("work_item_sha256") != reference.work_item_sha256
            or self.schema_payload.get("reference_bundle_sha256")
            != reference.logical_sha256
            or self.schema_payload.get("candidate_bundle_sha256")
            != candidate.logical_sha256
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: bundle/crosswalk provenance does not match"
            )
        crosswalk_cases = {
            item["case_id"]: item
            for item in self.schema_payload.get("cases", [])
            if isinstance(item, dict) and isinstance(item.get("case_id"), str)
        }
        candidate_by_id = {case.case_id: case for case in candidate_cases}
        certificate_by_id: dict[str, BusPriceCaseCertificate] = {}
        profile = REPORT_ROW_PARITY_PROFILE
        certificate_sha256 = None
        if self.bus_price_certificate is not None:
            certificate = self.bus_price_certificate
            certificate.validate()
            if (
                not certificate.passed
                or certificate.trading_date != trading_date
                or certificate.source_sha256 != reference.source_sha256
                or certificate.reference_bundle_sha256 != reference.logical_sha256
                or certificate.candidate_bundle_sha256 != candidate.logical_sha256
                or tuple(case.case_id for case in certificate.cases)
                != reference.affected_case_ids
            ):
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: bus-price certificate provenance does not match"
                )
            certificate_by_id = {case.case_id: case for case in certificate.cases}
            profile = REPORT_ROW_BUS_CERTIFIED_PROFILE
            certificate_sha256 = certificate.logical_sha256
        zero_flow_certificate_sha256 = None
        if self.zero_flow_price_certificate is not None:
            zero_flow = self.zero_flow_price_certificate
            zero_flow.validate()
            if (
                not zero_flow.passed
                or zero_flow.trading_date != trading_date
                or zero_flow.source_sha256 != reference.source_sha256
                or zero_flow.reference_bundle_sha256 != reference.logical_sha256
                or zero_flow.candidate_bundle_sha256 != candidate.logical_sha256
                or tuple(case.case_id for case in zero_flow.cases)
                != reference.affected_case_ids
            ):
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: zero-flow certificate provenance does not match"
                )
            profile = REPORT_ROW_ZERO_FLOW_CERTIFIED_PROFILE
            zero_flow_certificate_sha256 = zero_flow.logical_sha256
        cases = []
        for expected in reference_cases:
            actual = candidate_by_id[expected.case_id]
            recomputed = ReportSchemaCrosswalkValidator().compare(
                case_id=expected.case_id,
                reference=expected.surfaces["report-field"],
                candidate=actual.surfaces["report-field"],
            )
            if crosswalk_cases.get(expected.case_id) != recomputed.to_dict():
                raise EvidenceContractError(
                    "REQ-G12-REPORT-ROW: schema crosswalk case does not match"
                )
            cases.append(
                self.validator.compare(
                    case_id=expected.case_id,
                    reference=expected.surfaces["report-field"],
                    candidate=actual.surfaces["report-field"],
                    bus_price_certificate=certificate_by_id.get(expected.case_id),
                    zero_flow_price_certificate=self.zero_flow_price_certificate,
                )
            )
        unsigned = self._unsigned(
            profile,
            trading_date,
            reference.source_sha256,
            reference.work_item_sha256,
            reference.logical_sha256,
            candidate.logical_sha256,
            certificate_sha256,
            zero_flow_certificate_sha256,
            tuple(cases),
        )
        return ReportRowParityResult(
            profile=profile,
            trading_date=trading_date,
            source_sha256=reference.source_sha256,
            work_item_sha256=reference.work_item_sha256,
            reference_bundle_sha256=reference.logical_sha256,
            candidate_bundle_sha256=candidate.logical_sha256,
            schema_crosswalk_sha256=self.schema_sha256,
            bus_price_certificate_sha256=certificate_sha256,
            zero_flow_price_certificate_sha256=zero_flow_certificate_sha256,
            cases=tuple(cases),
            logical_sha256=_logical_sha256(unsigned),
        )

    def _unsigned(
        self,
        profile: str,
        trading_date: str,
        source_sha256: str,
        work_item_sha256: str,
        reference_bundle_sha256: str,
        candidate_bundle_sha256: str,
        bus_price_certificate_sha256: str | None,
        zero_flow_price_certificate_sha256: str | None,
        cases: tuple[ReportCaseRowParity, ...],
    ) -> dict[str, object]:
        result = ReportRowParityResult(
            profile,
            trading_date,
            source_sha256,
            work_item_sha256,
            reference_bundle_sha256,
            candidate_bundle_sha256,
            self.schema_sha256,
            bus_price_certificate_sha256,
            zero_flow_price_certificate_sha256,
            cases,
            "",
        )
        return result.to_dict(include_hash=False)

    @staticmethod
    def _load_crosswalk(path: Path) -> tuple[dict[str, Any], str]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: unreadable schema crosswalk"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError("REQ-G12-REPORT-ROW: invalid schema crosswalk")
        logical_sha256 = payload.pop("logical_sha256", None)
        if (
            payload.get("profile") != REPORT_SCHEMA_CROSSWALK_PROFILE
            or payload.get("scope") != "schema-only-no-row-value-parity-claim"
            or logical_sha256 != _logical_sha256(payload)
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: schema crosswalk hash/profile mismatch"
            )
        return payload, logical_sha256


class ReportRowParityResultStore:
    """Atomically persist one immutable mapped-row comparison."""

    def load(self, source: Path) -> dict[str, Any]:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: unreadable result"
            ) from error
        if not isinstance(payload, dict):
            raise EvidenceContractError("REQ-G12-REPORT-ROW: invalid result")
        unsigned = dict(payload)
        logical_sha256 = unsigned.pop("logical_sha256", None)
        if (
            payload.get("profile")
            not in {
                REPORT_ROW_PARITY_PROFILE,
                REPORT_ROW_BUS_CERTIFIED_PROFILE,
                REPORT_ROW_ZERO_FLOW_CERTIFIED_PROFILE,
            }
            | _LEGACY_REPORT_ROW_PROFILES
            or payload.get("scope")
            != "mapped-fields-at-governed-portable-profile-precision"
            or logical_sha256 != _logical_sha256(unsigned)
        ):
            raise EvidenceContractError(
                "REQ-G12-REPORT-ROW: result hash/profile mismatch"
            )
        return payload

    def write(self, result: ReportRowParityResult, target: Path) -> Path:
        if result.logical_sha256 != _logical_sha256(result.to_dict(include_hash=False)):
            raise EvidenceContractError("REQ-G12-REPORT-ROW: result hash mismatch")
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        if target.exists() or temporary.exists():
            raise EvidenceContractError("REQ-G12-REPORT-ROW: result already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target
