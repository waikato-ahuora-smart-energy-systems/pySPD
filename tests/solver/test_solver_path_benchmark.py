from types import SimpleNamespace

from pyspd.orchestration import OrchestrationError
from tools.benchmark_solver_paths import (
    _execute_with_retries,
    _finish_payload,
    _published_price_rows,
)
from tools.compare_cplex_reference import (
    _accumulate_table_total,
    _base_node_candidate_rows,
    _load_reference,
)
from tools.gate12.report_row_parity import ReportValueDifference


def test_case_execution_retries_only_orchestration_failures() -> None:
    attempts = 0

    def execute() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OrchestrationError("transient native solver failure")
        return "optimal"

    retries: list[tuple[int, str]] = []
    result = _execute_with_retries(
        execute,
        maximum_attempts=2,
        on_retry=lambda attempt, error: retries.append((attempt, str(error))),
    )

    assert result == "optimal"
    assert attempts == 2
    assert retries == [(1, "transient native solver failure")]


def test_case_execution_raises_after_retry_limit() -> None:
    attempts = 0

    def execute() -> None:
        nonlocal attempts
        attempts += 1
        raise OrchestrationError("persistent native solver failure")

    try:
        _execute_with_retries(execute, maximum_attempts=2, on_retry=lambda *_: None)
    except OrchestrationError as error:
        assert str(error) == "persistent native solver failure"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("persistent failure was not raised")
    assert attempts == 2


def test_base_node_rows_average_all_cases_in_each_trading_period() -> None:
    records = (
        {
            "trading_period": "TP1",
            "reports": {
                "node": [
                    {
                        "node": "N1",
                        "generation_mw": "10",
                        "load_mw": "4",
                        "price_nzd_per_mwh": "50",
                    }
                ]
            },
        },
        {
            "trading_period": "TP1",
            "reports": {
                "node": [
                    {
                        "node": "N1",
                        "generation_mw": "14",
                        "load_mw": "6",
                        "price_nzd_per_mwh": "54",
                    }
                ]
            },
        },
    )
    reference_rows = (
        {"DateTime": "02-Aug-2023 00:00", "TP": "TP1", "Node": "N1"},
    )

    assert _base_node_candidate_rows(records, reference_rows) == [
        {
            "case_id": "base",
            "date_time": "02-Aug-2023 00:00",
            "node": "N1",
            "generation_mw": "12",
            "load_mw": "5",
            "price_nzd_per_mwh": "52",
        }
    ]


def test_2023_base_node_reference_uses_governed_node_table_suffix(tmp_path) -> None:
    (tmp_path / "2023-08-02_base_node_results.csv").write_text(
        "DateTime,TP,Node,Generation (MW),Load (MW),Price ($/MWh)\n"
        "02-Aug-2023 00:00,TP1,N1,1,2,3\n",
        encoding="utf-8",
    )

    loaded = _load_reference(tmp_path, year=2023)

    assert "Base_NodeResults_TP" in loaded


def test_fastest_completed_optimal_is_separate_from_strict_qualification() -> None:
    payload = {
        "runs": [
            {
                "profile": "scip-mip-fixed-highs-rmip",
                "completed": True,
                "all_solves_optimal": True,
                "independent_validation_passed": False,
                "solve_seconds": 100.0,
                "parity": {
                    "market_result_parity_passed": True,
                    "strict_raw_parity_passed": True,
                },
            },
            {
                "profile": "scip-mip-fixed-clp-rmip",
                "completed": True,
                "all_solves_optimal": True,
                "independent_validation_passed": False,
                "solve_seconds": 92.0,
                "parity": {
                    "market_result_parity_passed": False,
                    "strict_raw_parity_passed": False,
                },
            },
            {
                "profile": "cbc-mip-fixed-clp-rmip",
                "completed": False,
                "solve_seconds": 5.0,
                "parity": {},
            },
        ]
    }

    _finish_payload(payload)

    assert payload["fastest_completed_optimal_profile"] == ("scip-mip-fixed-clp-rmip")
    assert payload["fastest_optimal_validated_profile"] is None
    assert payload["fastest_strict_raw_parity_profile"] is None


def test_published_price_rows_preserve_energy_reserve_weights_and_identity() -> None:
    rows = _published_price_rows(
        SimpleNamespace(
            energy={("TP1", "NODE"): 12.34568},
            energy_intervals={("TP1", "NODE"): (12.3, 12.4)},
            reserve={("TP1", "NI", "FIR"): 0.125},
            total_seconds={"TP1": 300.0},
            date_time={"TP1": "01-JAN-2024 00:00"},
        )
    )

    assert rows == [
        {
            "trading_period": "TP1",
            "location": "NODE",
            "product": "energy",
            "price_nzd_per_mwh": "12.34568",
            "price_interval": "[12.300000000000001,12.4]",
            "publication_seconds": "300",
            "date_time": "01-JAN-2024 00:00",
        },
        {
            "trading_period": "TP1",
            "location": "NI",
            "product": "FIR",
            "price_nzd_per_mwh": "0.125",
            "price_interval": "",
            "publication_seconds": "300",
            "date_time": "01-JAN-2024 00:00",
        },
    ]


def test_cplex_table_total_retains_auditable_maximum_identity() -> None:
    difference = ReportValueDifference(
        observable="system-ofv",
        identity=("case", "time", "system-ofv"),
        reference_value="100",
        candidate_value="103",
        absolute_error="3",
        authority_half_unit="0.5",
    )
    table = SimpleNamespace(
        reference_table="SummaryResults_TP",
        candidate_table="summary",
        compared_value_count=1,
        missing_identity_count=0,
        extra_identity_count=0,
        certified_difference_count=0,
        above_precision_count=1,
        maximum_absolute_error="3",
        maximum_difference=difference,
    )
    totals = {}

    _accumulate_table_total(totals, table)

    assert totals["SummaryResults_TP"]["maximum_difference"] == {
        "observable": "system-ofv",
        "identity": ["case", "time", "system-ofv"],
        "reference_value": "100",
        "candidate_value": "103",
        "absolute_error": "3",
        "authority_half_unit": "0.5",
    }
