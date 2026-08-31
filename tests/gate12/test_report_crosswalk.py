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
    assert table.unmapped_candidate_fields == ("dead",)
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
