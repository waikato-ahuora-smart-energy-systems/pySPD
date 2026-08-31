"""Probity tests for mapped Authority/PySPD report-row parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.report_row_parity import (
    ReportRowParityRunner,
    ReportRowParityValidator,
    _logical_sha256,
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
