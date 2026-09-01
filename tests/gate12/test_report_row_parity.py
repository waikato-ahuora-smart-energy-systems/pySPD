"""Probity tests for mapped Authority/PySPD report-row parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.gate12.bus_price_degeneracy import BusPriceCaseCertificate
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.report_row_parity import (
    ReportRowParityRunner,
    ReportRowParityValidator,
    _logical_sha256,
)
from tools.gate12.zero_flow_price_convention import (
    ZeroFlowBusObservation,
    ZeroFlowCaseCertificate,
    ZeroFlowPriceConventionResult,
)


def _json(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def test_node_rows_compare_at_authority_display_precision() -> None:
    reference = _json(
        {
            "prefix_NodeResults_TP": {
                "fields": ["CaseID", "DateTime", "Node", "Price ($/MWh)"],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Node": "NODE",
                        "Price ($/MWh)": "13.1820",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "node": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "node",
                    "price_nzd_per_mwh",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "node": "NODE",
                        "price_nzd_per_mwh": "13.18204",
                    }
                ],
            }
        }
    )

    result = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert result.passed
    assert result.tables[0].compared_value_count == 1
    assert result.tables[0].maximum_absolute_error == "0.00004"


def test_node_row_above_half_display_unit_fails() -> None:
    reference = _json(
        {
            "prefix_NodeResults_TP": {
                "fields": ["CaseID", "DateTime", "Node", "Price ($/MWh)"],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Node": "NODE",
                        "Price ($/MWh)": "13.1820",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "node": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "node",
                    "price_nzd_per_mwh",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "node": "NODE",
                        "price_nzd_per_mwh": "13.18206",
                    }
                ],
            }
        }
    )

    result = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert not result.passed
    assert result.tables[0].above_precision_count == 1


def test_branch_endpoint_price_uses_governed_portable_price_tolerance() -> None:
    reference = _json(
        {
            "prefix_BranchResults_TP": {
                "fields": [
                    "CaseID",
                    "DateTime",
                    "Branch",
                    "FromBus",
                    "ToBus",
                    "FromBusPrice ($/MWh)",
                ],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Branch": "LINE",
                        "FromBus": "A",
                        "ToBus": "B",
                        "FromBusPrice ($/MWh)": "10.00000",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "branch": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "branch",
                    "from_bus",
                    "to_bus",
                    "from_bus_price_nzd_per_mwh",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "branch": "LINE",
                        "from_bus": "A",
                        "to_bus": "B",
                        "from_bus_price_nzd_per_mwh": "10.0009",
                    }
                ],
            }
        }
    )

    result = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert result.passed
    assert result.tables[0].certified_difference_count == 1


@pytest.mark.parametrize(
    ("reference_table", "location_field", "price_field", "product"),
    (
        (
            "PublishedEnergyPrices_TP",
            "Pnodename",
            "vSPDDollarsPerMegawattHour",
            "energy",
        ),
        (
            "PublishedReservePrices_TP",
            "Island",
            "vSPDSIRDollarsPerMegawattHour",
            "SIR",
        ),
    ),
)
def test_published_price_rows_use_governed_portable_price_tolerance(
    reference_table: str,
    location_field: str,
    price_field: str,
    product: str,
) -> None:
    reference = _json(
        {
            f"prefix_{reference_table}": {
                "fields": [
                    "DateTime",
                    "TradingPeriod",
                    location_field,
                    price_field,
                ],
                "rows": [
                    {
                        "DateTime": "time",
                        "TradingPeriod": "TP1",
                        location_field: "LOCATION",
                        price_field: "10.00000",
                    }
                ],
            }
        }
    )

    def candidate(value: str) -> bytes:
        return _json(
            {
                "published_price": {
                    "field_order": [
                        "date_time",
                        "trading_period",
                        "location",
                        "product",
                        "price_nzd_per_mwh",
                    ],
                    "fields": [],
                    "rows": [
                        {
                            "date_time": "time",
                            "trading_period": "TP1",
                            "location": "LOCATION",
                            "product": product,
                            "price_nzd_per_mwh": value,
                        }
                    ],
                }
            }
        )

    within = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate("10.00009")
    )
    above = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate("10.00011")
    )

    assert within.passed
    assert within.tables[0].certified_difference_count == 1
    assert not above.passed
    assert above.tables[0].above_precision_count == 1


def test_offer_reserve_alternative_allocation_requires_equal_aggregate() -> None:
    reference = _json(
        {
            "prefix_OfferResults_TP": {
                "fields": ["CaseID", "DateTime", "Offer", "Trader", "FIR (MW)"],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Offer": "A",
                        "Trader": "T",
                        "FIR (MW)": "1.0000",
                    },
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Offer": "B",
                        "Trader": "T",
                        "FIR (MW)": "2.0000",
                    },
                ],
            }
        }
    )

    def candidate(second: str) -> bytes:
        return _json(
            {
                "offer": {
                    "field_order": [
                        "case_id",
                        "date_time",
                        "offer",
                        "trader",
                        "fir_mw",
                    ],
                    "fields": [],
                    "rows": [
                        {
                            "case_id": "case",
                            "date_time": "time",
                            "offer": "A",
                            "trader": "T",
                            "fir_mw": "2.5",
                        },
                        {
                            "case_id": "case",
                            "date_time": "time",
                            "offer": "B",
                            "trader": "T",
                            "fir_mw": second,
                        },
                    ],
                }
            }
        )

    equivalent = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate("0.5")
    )
    unequal = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate("0.6")
    )

    assert equivalent.passed
    assert equivalent.tables[0].certified_difference_count == 2
    assert not unequal.passed
    assert unequal.tables[0].above_precision_count == 2


def test_named_zero_flow_node_certificate_classifies_report_difference() -> None:
    reference = _json(
        {
            "prefix_NodeResults_TP": {
                "fields": ["CaseID", "DateTime", "Node", "Price ($/MWh)"],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Node": "NODE",
                        "Price ($/MWh)": "9.9900",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "node": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "node",
                    "price_nzd_per_mwh",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "node": "NODE",
                        "price_nzd_per_mwh": "10.01001001001001",
                    }
                ],
            }
        }
    )
    observation = ZeroFlowBusObservation(
        bus="LEAF",
        branch="LINE",
        parent_bus="PARENT",
        inward_direction="forward",
        first_inward_loss_factor=0.001,
        first_outward_loss_factor=0.001,
        reference_price=9.99,
        candidate_price=10.0 / 0.999,
        expected_load_derivative=10.0 / 0.999,
        expected_export_derivative=9.99,
        candidate_residual=0.0,
        reference_residual=0.0,
        reference_side="export",
        zero_flow_evidence="reported-branch-flow",
    )
    case = ZeroFlowCaseCertificate(
        case_id="case",
        date_time="time",
        observations=(observation,),
        material_bus_identities=("LEAF",),
        certified_node_identities=("NODE",),
        unresolved_bus_reasons={},
        unresolved_node_reasons={},
        maximum_node_projection_residual=0.0,
        price_tolerance=1e-4,
        analytic_tolerance=1e-9,
        projection_tolerance=1e-10,
    )
    certificate = ZeroFlowPriceConventionResult.create(
        trading_date="20221106",
        source_sha256="1" * 64,
        reference_result_gdx_sha256="2" * 64,
        reference_bundle_sha256="3" * 64,
        candidate_bundle_sha256="4" * 64,
        topology_sha256="5" * 64,
        cases=(case,),
        publications=(),
    )

    result = ReportRowParityValidator().compare(
        case_id="case",
        reference=reference,
        candidate=candidate,
        zero_flow_price_certificate=certificate,
    )

    assert result.passed
    assert result.tables[0].certified_difference_count == 1
    assert result.tables[0].above_precision_count == 0


def test_reserve_wide_to_long_pivot_is_identity_strict() -> None:
    reference = _json(
        {
            "prefix_ReserveResults_TP": {
                "fields": [
                    "CaseID",
                    "DateTime",
                    "Island",
                    "FIR Price ($/MW)",
                    "SIR Price ($/MW)",
                ],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Island": "NI",
                        "FIR Price ($/MW)": "0.050",
                        "SIR Price ($/MW)": "0.070",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "reserve": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "island",
                    "reserve_class",
                    "price_nzd_per_mwh",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "island": "NI",
                        "reserve_class": "FIR",
                        "price_nzd_per_mwh": "0.0504",
                    },
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "island": "NI",
                        "reserve_class": "SIR",
                        "price_nzd_per_mwh": "0.0704",
                    },
                ],
            }
        }
    )

    result = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert result.passed
    assert result.tables[0].compared_value_count == 2
    assert result.tables[0].missing_identity_count == 0


def test_missing_candidate_identity_is_not_treated_as_zero() -> None:
    reference = _json(
        {
            "prefix_OfferResults_TP": {
                "fields": [
                    "CaseID",
                    "DateTime",
                    "Offer",
                    "Trader",
                    "Generation (MW)",
                ],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Offer": "OFFER",
                        "Trader": "TRADER",
                        "Generation (MW)": "0.0000",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "offer": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "offer",
                    "trader",
                    "generation_mw",
                ],
                "fields": [],
                "rows": [],
            }
        }
    )

    result = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert not result.passed
    assert result.tables[0].missing_identity_count == 1
    assert result.tables[0].missing_identity_examples == (
        ("case", "time", "OFFER", "TRADER", "generation-mw"),
    )


def test_row_runner_rejects_tampered_schema_crosswalk(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "profile": "authority-pyspd-report-schema-crosswalk-v1",
        "scope": "schema-only-no-row-value-parity-claim",
        "cases": [],
    }
    payload["logical_sha256"] = _logical_sha256(payload)
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    payload["cases"] = [{"case_id": "tampered"}]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvidenceContractError, match="hash/profile mismatch"):
        ReportRowParityRunner._load_crosswalk(path)


def test_constraint_rows_derive_rhs_and_sense_from_pyomo_bounds() -> None:
    reference = _json(
        {
            "prefix_BrConstraintResults_TP": {
                "fields": [
                    "CaseID",
                    "DateTime",
                    "BranchConstraint",
                    "LHS (MW)",
                    "Sense (-1:<=, 0:=, 1:>=)",
                    "RHS (MW)",
                ],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "BranchConstraint": "LIMIT",
                        "LHS (MW)": "10.00000",
                        "Sense (-1:<=, 0:=, 1:>=)": "-1.00000",
                        "RHS (MW)": "20.00000",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "constraint": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "constraint",
                    "index",
                    "body",
                    "lower",
                    "upper",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "constraint": "NetworkSecurity.BranchSecurityConstraintLE",
                        "index": "case|time|LIMIT",
                        "body": "10.000004",
                        "lower": "",
                        "upper": "20",
                    }
                ],
            }
        }
    )

    result = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert result.passed
    assert result.tables[0].compared_value_count == 3
    assert result.tables[0].observables == (
        "branch-constraint-lhs",
        "branch-constraint-rhs",
        "branch-constraint-sense",
    )


def test_passing_bus_certificate_classifies_report_price_difference() -> None:
    reference = _json(
        {
            "prefix_BusResults_TP": {
                "fields": ["CaseID", "DateTime", "Bus", "Price ($/MWh)"],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Bus": "BUS",
                        "Price ($/MWh)": "10.000",
                    }
                ],
            }
        }
    )
    candidate = _json(
        {
            "bus": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "bus",
                    "repaired_price_nzd_per_mwh",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "bus": "BUS",
                        "repaired_price_nzd_per_mwh": "11",
                    }
                ],
            }
        }
    )
    certificate = BusPriceCaseCertificate(
        case_id="case",
        allocation_sha256="0" * 64,
        bus_count=1,
        node_count=1,
        allocation_count=1,
        normalized_raw_sentinel_count=0,
        above_tolerance_raw_bus_count=0,
        above_tolerance_repaired_bus_count=1,
        maximum_raw_bus_absolute_difference=0.0,
        maximum_repaired_bus_absolute_difference=1.0,
        maximum_raw_projected_node_difference=0.0,
        maximum_repaired_projected_node_difference=0.0,
        maximum_node_absolute_difference=0.0,
        maximum_projection_residual=0.0,
        price_tolerance=1e-4,
        projection_tolerance=1e-10,
    )

    result = ReportRowParityValidator().compare(
        case_id="case",
        reference=reference,
        candidate=candidate,
        bus_price_certificate=certificate,
    )

    assert result.passed
    assert result.tables[0].certified_difference_count == 1
    assert result.tables[0].above_precision_count == 0


def test_risk_and_summary_rows_compare_every_authority_numeric_field() -> None:
    risk_identity = {
        "CaseID": "case",
        "DateTime": "time",
        "Island": "NI",
        "ReserveClass": "FIR",
        "RiskClass": "CE",
        "RiskType": "GEN",
        "RiskSetter": "OFFER",
    }
    risk_values = {
        "CoveredEnergy": "137.0000",
        "CoveredReserve": "1.2500",
        "CoveredFKBand": "0.5000",
        "RiskSubtractor": "2.0000",
        "Reserve": "140.0000",
        "Shortfall": "0.0000",
        "Deficit": "0.0000",
        "ReservePrice": "0.0085",
        "RiskPrice": "0.0001",
    }
    summary_values = {
        "SolveStatus (1=OK)": "1.00000",
        "SystemOFV": "1000.00000",
        "SystemCost": "20.00000",
        "SystemBenefit": "1.00000",
        "ViolationCost": "0.50000",
        "DeficitGenViol (MW)": "0.00000",
        "SurplusGenViol (MW)": "0.00000",
        "DeficitReserveViol (MW)": "0.00000",
        "SurplusBranchFlowViol (MW)": "0.00000",
        "DeficitRampRateViol (MW)": "0.00000",
        "SurplusRampRateViol (MW)": "0.00000",
        "DeficitBranchGroupConstraintViol (MW)": "0.00000",
        "SurplusBranchGroupConstraintViol (MW)": "0.00000",
        "DeficitMNodeConstraintViol (MW)": "0.00000",
        "SurplusMNodeConstraintViol (MW)": "0.00000",
    }
    reference = _json(
        {
            "prefix_RiskResults_TP": {
                "fields": [*risk_identity, *risk_values],
                "rows": [{**risk_identity, **risk_values}],
            },
            "prefix_SummaryResults_TP": {
                "fields": ["CaseID", "DateTime", *summary_values],
                "rows": [{"CaseID": "case", "DateTime": "time", **summary_values}],
            },
        }
    )
    candidate = _json(
        {
            "risk": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "island",
                    "reserve_class",
                    "risk_class",
                    "risk_type",
                    "risk_setter",
                    "covered_energy_mw",
                    "covered_reserve_mw",
                    "covered_fk_band_mw",
                    "risk_subtractor_mw",
                    "reserve_mw",
                    "shortfall_mw",
                    "deficit_mw",
                    "reserve_price_nzd_per_mwh",
                    "risk_price_nzd_per_mwh",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "island": "NI",
                        "reserve_class": "FIR",
                        "risk_class": "CE",
                        "risk_type": "GEN",
                        "risk_setter": "OFFER",
                        "covered_energy_mw": "137",
                        "covered_reserve_mw": "1.25",
                        "covered_fk_band_mw": "0.5",
                        "risk_subtractor_mw": "2",
                        "reserve_mw": "140",
                        "shortfall_mw": "0",
                        "deficit_mw": "0",
                        "reserve_price_nzd_per_mwh": "0.0085",
                        "risk_price_nzd_per_mwh": "0.0001",
                    }
                ],
            },
            "summary": {
                "field_order": [
                    "case_id",
                    "date_time",
                    "status_code",
                    "system_ofv_nzd",
                    "system_cost_nzd",
                    "system_benefit_nzd",
                    "violation_cost_nzd",
                    "deficit_generation_mw",
                    "surplus_generation_mw",
                    "deficit_reserve_mw",
                    "surplus_branch_flow_mw",
                    "deficit_ramp_rate_mw",
                    "surplus_ramp_rate_mw",
                    "deficit_branch_constraint_mw",
                    "surplus_branch_constraint_mw",
                    "deficit_market_node_constraint_mw",
                    "surplus_market_node_constraint_mw",
                ],
                "fields": [],
                "rows": [
                    {
                        "case_id": "case",
                        "date_time": "time",
                        "status_code": "1",
                        "system_ofv_nzd": "1000",
                        "system_cost_nzd": "20",
                        "system_benefit_nzd": "1",
                        "violation_cost_nzd": "0.5",
                        "deficit_generation_mw": "0",
                        "surplus_generation_mw": "0",
                        "deficit_reserve_mw": "0",
                        "surplus_branch_flow_mw": "0",
                        "deficit_ramp_rate_mw": "0",
                        "surplus_ramp_rate_mw": "0",
                        "deficit_branch_constraint_mw": "0",
                        "surplus_branch_constraint_mw": "0",
                        "deficit_market_node_constraint_mw": "0",
                        "surplus_market_node_constraint_mw": "0",
                    }
                ],
            },
        }
    )

    result = ReportRowParityValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert result.passed
    assert not result.unimplemented_reference_tables
    assert sum(table.compared_value_count for table in result.tables) == 24
