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
                    "Generation (MW)",
                ],
                "rows": [
                    {
                        "CaseID": "case",
                        "DateTime": "time",
                        "Offer": "OFFER",
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
        ("case", "time", "OFFER", "generation-mw"),
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
