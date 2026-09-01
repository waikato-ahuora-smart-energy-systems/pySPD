"""Probity tests for the Authority-to-PySPD report schema crosswalk."""

from __future__ import annotations

import json

import pytest

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.report_crosswalk import ReportSchemaCrosswalkValidator


def _json(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def test_crosswalk_classifies_direct_and_unsupported_fields() -> None:
    reference = _json(
        {
            "gate12_ref_20221106_NodeResults_TP": {
                "fields": [
                    "CaseID",
                    "DateTime",
                    "Node",
                    "Price ($/MWh)",
                    "Generation (MW)",
                ],
                "rows": [],
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
                    "dead",
                ],
                "fields": [],
                "rows": [],
            }
        }
    )

    result = ReportSchemaCrosswalkValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    table = result.tables[0]
    assert table.reference_table == "NodeResults_TP"
    assert table.candidate_table == "node"
    assert table.mapped_reference_fields == 4
    assert table.unmapped_reference_fields == ("Generation (MW)",)
    assert table.unmapped_candidate_fields == ()
    assert not result.passed


def test_crosswalk_recognizes_pivoted_reserve_prices() -> None:
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
                "rows": [],
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
                "rows": [],
            }
        }
    )

    result = ReportSchemaCrosswalkValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert result.passed
    assert result.tables[0].mapping_kinds == {"direct": 3, "pivot": 2}


def test_crosswalk_maps_complete_risk_and_summary_contracts() -> None:
    reference = _json(
        {
            "prefix_RiskResults_TP": {
                "fields": [
                    "CaseID",
                    "DateTime",
                    "Period",
                    "Island",
                    "ReserveClass",
                    "RiskClass",
                    "RiskType",
                    "RiskSetter",
                    "CoveredEnergy",
                    "CoveredReserve",
                    "CoveredFKBand",
                    "RiskSubtractor",
                    "Reserve",
                    "Shortfall",
                    "Deficit",
                    "ReservePrice",
                    "RiskPrice",
                ],
                "rows": [],
            },
            "prefix_SummaryResults_TP": {
                "fields": [
                    "CaseID",
                    "DateTime",
                    "Period",
                    "SolveStatus (1=OK)",
                    "SystemOFV",
                    "SystemCost",
                    "SystemBenefit",
                    "ViolationCost",
                    "DeficitGenViol (MW)",
                    "SurplusGenViol (MW)",
                    "DeficitReserveViol (MW)",
                    "SurplusBranchFlowViol (MW)",
                    "DeficitRampRateViol (MW)",
                    "SurplusRampRateViol (MW)",
                    "DeficitBranchGroupConstraintViol (MW)",
                    "SurplusBranchGroupConstraintViol (MW)",
                    "DeficitMNodeConstraintViol (MW)",
                    "SurplusMNodeConstraintViol (MW)",
                ],
                "rows": [],
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
                "rows": [],
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
                "rows": [],
            },
        }
    )

    result = ReportSchemaCrosswalkValidator().compare(
        case_id="case", reference=reference, candidate=candidate
    )

    assert result.passed
    assert all(table.passed for table in result.tables)


def test_crosswalk_fails_closed_on_duplicate_reference_suffix() -> None:
    reference = _json(
        {
            "first_NodeResults_TP": {"fields": ["CaseID"], "rows": []},
            "second_NodeResults_TP": {"fields": ["CaseID"], "rows": []},
        }
    )
    candidate = _json(
        {
            "node": {
                "field_order": ["case_id"],
                "fields": [],
                "rows": [],
            }
        }
    )

    with pytest.raises(EvidenceContractError, match="duplicate reference table"):
        ReportSchemaCrosswalkValidator().compare(
            case_id="case", reference=reference, candidate=candidate
        )


def test_crosswalk_fails_closed_on_malformed_candidate_schema() -> None:
    reference = _json({"prefix_NodeResults_TP": {"fields": ["CaseID"], "rows": []}})
    candidate = _json({"node": {"fields": [], "rows": []}})

    with pytest.raises(EvidenceContractError, match="malformed candidate table"):
        ReportSchemaCrosswalkValidator().compare(
            case_id="case", reference=reference, candidate=candidate
        )


def test_crosswalk_rejects_duplicate_json_keys() -> None:
    reference = b'{"a_NodeResults_TP":{"fields":["CaseID"]},"a_NodeResults_TP":{"fields":["CaseID"]}}'
    candidate = _json({"node": {"field_order": ["case_id"], "fields": [], "rows": []}})

    with pytest.raises(EvidenceContractError, match="duplicate reference JSON key"):
        ReportSchemaCrosswalkValidator().compare(
            case_id="case", reference=reference, candidate=candidate
        )
