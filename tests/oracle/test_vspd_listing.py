from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.oracle.vspd import (
    BaselineComparison,
    DpsNodePriceParser,
    ListingParseError,
    ObjectiveBaseline,
    PriceReportError,
    ScipHighsPricingProfile,
    VspdListingParser,
)

LISTING = """
Solution Report     SOLVE vSPD_NMIR Using MIP From line 6602
     MODEL   vSPD_NMIR           OBJECTIVE  NETBENEFIT
     SOLVER  SCIP                FROM LINE  6602
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS      1 Optimal
**** OBJECTIVE VALUE         100.0000

Solution Report     SOLVE vSPD_NMIR Using RMIP From line 6603
     MODEL   vSPD_NMIR           OBJECTIVE  NETBENEFIT
     SOLVER  HIGHS               FROM LINE  6603
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS      1 Optimal
**** OBJECTIVE VALUE         99.9999

LOOPS                                  drs   increase conforming load 0.5%
Solution Report     SOLVE vSPD_NMIR Using MIP From line 6602
     MODEL   vSPD_NMIR           OBJECTIVE  NETBENEFIT
     SOLVER  SCIP                FROM LINE  6602
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS      1 Optimal
**** OBJECTIVE VALUE         101.2500

LOOPS                                  drs   decrease conforming load 5.0%
Solution Report     SOLVE vSPD_NMIR Using MIP From line 6602
     MODEL   vSPD_NMIR           OBJECTIVE  NETBENEFIT
     SOLVER  SCIP                FROM LINE  6602
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS      1 Optimal
**** OBJECTIVE VALUE         92.5000

Solution Report     SOLVE vSPD_BranchFlowMIP Using MIP From line 1179
     MODEL   vSPD_BranchFlowMIP  OBJECTIVE  NETBENEFIT
     SOLVER  SCIP                FROM LINE  1179
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS      1 Optimal
**** OBJECTIVE VALUE         92.5000
"""

CONVERT_REPORT = """
Solution Report     SOLVE vSPD_NMIR Using RMIP From line 7283
     MODEL   vSPD_NMIR           OBJECTIVE  NETBENEFIT
     SOLVER  CONVERT             FROM LINE  7283
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS     14 No Solution Returned
**** OBJECTIVE VALUE         99.9999
"""

ADDITIONAL_PRICING_REPORTS = """
LOOPS                                  drs   increase conforming load 0.5%
Solution Report     SOLVE vSPD_NMIR Using RMIP From line 6603
     MODEL   vSPD_NMIR           OBJECTIVE  NETBENEFIT
     SOLVER  HIGHS               FROM LINE  6603
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS      1 Optimal
**** OBJECTIVE VALUE         101.2500

LOOPS                                  drs   decrease conforming load 5.0%
Solution Report     SOLVE vSPD_NMIR Using RMIP From line 6603
     MODEL   vSPD_NMIR           OBJECTIVE  NETBENEFIT
     SOLVER  HIGHS               FROM LINE  6603
**** SOLVER STATUS     1 Normal Completion
**** MODEL STATUS      1 Optimal
**** OBJECTIVE VALUE         92.5000
"""


def test_parser_keeps_primary_and_cleanup_solves_distinct() -> None:
    result = VspdListingParser().parse_text(LISTING)

    assert [record.scenario for record in result.primary] == [
        "base",
        "increase conforming load 0.5%",
        "decrease conforming load 5.0%",
    ]
    assert [record.objective for record in result.primary] == [100.0, 101.25, 92.5]
    assert len(result.cleanup) == 1
    assert result.cleanup[0].model == "vSPD_BranchFlowMIP"
    assert len(result.pricing) == 1
    assert result.pricing[0].solver == "HIGHS"
    assert result.pricing[0].solve_type == "RMIP"
    assert result.pricing[0].objective == pytest.approx(99.9999)
    assert result.all_optimal


def test_parser_classifies_convert_as_export_not_operational_solve() -> None:
    result = VspdListingParser().parse_text(LISTING + CONVERT_REPORT)

    assert len(result.exports) == 1
    assert result.exports[0].solver == "CONVERT"
    assert len(result.pricing) == 1
    assert result.all_optimal


def test_profile_match_rejects_wrong_pricing_solver() -> None:
    qualified = LISTING + ADDITIONAL_PRICING_REPORTS + CONVERT_REPORT
    assert (
        VspdListingParser()
        .parse_text(qualified)
        .matches_profile(ScipHighsPricingProfile())
    )

    wrong = qualified.replace("SOLVER  HIGHS", "SOLVER  CPLEX")

    assert (
        not VspdListingParser()
        .parse_text(wrong)
        .matches_profile(ScipHighsPricingProfile())
    )


def test_parser_rejects_listing_without_solution_reports() -> None:
    with pytest.raises(ListingParseError, match="no GAMS solution reports"):
        VspdListingParser().parse_text("normal completion without a solve")


def test_baseline_comparison_reports_worst_delta(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "case": "fixture",
                "source": {},
                "objectives": [
                    {"scenario": "base", "value": 100.0},
                    {
                        "scenario": "increase conforming load 0.5%",
                        "value": 101.2499,
                    },
                    {"scenario": "decrease conforming load 5.0%", "value": 92.5},
                ],
            }
        )
    )

    baseline = ObjectiveBaseline.load(path)
    comparison = BaselineComparison.compare(
        actual=VspdListingParser().parse_text(LISTING).primary,
        expected=baseline,
        absolute_tolerance=0.001,
        relative_tolerance=1e-10,
    )

    assert comparison.passed
    assert comparison.max_absolute_delta == pytest.approx(0.0001)
    assert comparison.worst_scenario == "increase conforming load 0.5%"


def test_baseline_comparison_requires_identical_scenario_order(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "case": "fixture",
                "source": {},
                "objectives": [
                    {"scenario": "wrong", "value": 100.0},
                    {
                        "scenario": "increase conforming load 0.5%",
                        "value": 101.25,
                    },
                    {"scenario": "decrease conforming load 5.0%", "value": 92.5},
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="scenario sequence"):
        BaselineComparison.compare(
            actual=VspdListingParser().parse_text(LISTING).primary,
            expected=ObjectiveBaseline.load(path),
        )


def test_node_price_parser_requires_unique_finite_keys() -> None:
    report = DpsNodePriceParser().parse_text(
        '"DateTime","Scenario","Node","Price"\n'
        '"26-FEB-2025 11:55","base","BEN2201",247.949\n'
        '"26-FEB-2025 11:55","base","HAY2201",81.253\n'
    )

    assert report.scenario_count == 1
    assert report.node_count == 2
    assert report.minimum_price == pytest.approx(81.253)
    assert report.maximum_price == pytest.approx(247.949)


@pytest.mark.parametrize("price", ["NA", "INF", "-INF", "UNDF"])
def test_node_price_parser_rejects_non_finite_gams_values(price: str) -> None:
    with pytest.raises(PriceReportError, match="non-finite"):
        DpsNodePriceParser().parse_text(
            '"DateTime","Scenario","Node","Price"\n'
            f'"26-FEB-2025 11:55","base","BEN2201",{price}\n'
        )


def test_node_price_parser_rejects_duplicate_keys() -> None:
    row = '"26-FEB-2025 11:55","base","BEN2201",247.949\n'
    with pytest.raises(PriceReportError, match="duplicate"):
        DpsNodePriceParser().parse_text(
            '"DateTime","Scenario","Node","Price"\n' + row + row
        )
