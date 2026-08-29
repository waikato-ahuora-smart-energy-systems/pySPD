"""Probity tests for algebraic historical shortfall enumeration."""

from __future__ import annotations

from tools.gate12.analytic_population import (
    HistoricalAnalyticPopulationSelector,
    HistoricalFirstLoopCase,
    HistoricalFirstLoopLoadReconstructor,
)


def test_first_loop_reconstruction_identifies_scaled_dead_node_shortfall() -> None:
    case = HistoricalFirstLoopCase(
        case_id="case_1",
        date_time="06-NOV-2022 07:00",
        trading_period="TP15",
        shortfall_transfer_enabled=True,
        use_actual_load=True,
        island_parameters={
            ("NI", "MWIPS"): 110.0,
            ("NI", "PSD"): 0.0,
            ("NI", "Losses"): 10.0,
        },
        node_parameters={
            ("DEAD", "initialLoad"): 4.5,
            ("DEAD", "conformingFactor"): 4.5,
            ("LIVE", "initialLoad"): 93.5,
            ("LIVE", "conformingFactor"): 93.5,
        },
        node_market_islands={"DEAD": ("NI",), "LIVE": ("NI",)},
        node_electrical_island_sum={"DEAD": 0.0, "LIVE": 1.0},
    )

    result = HistoricalFirstLoopLoadReconstructor().reconstruct(case)

    assert result.required_load["DEAD"] == 4.591836734693878
    assert result.affected_shortfall_mw == {"DEAD": 4.591836734693878}


def test_first_loop_reconstruction_applies_estimated_load_and_eligibility() -> None:
    case = HistoricalFirstLoopCase(
        case_id="case_2",
        date_time="06-NOV-2022 07:05",
        trading_period="TP15",
        shortfall_transfer_enabled=True,
        use_actual_load=True,
        island_parameters={
            ("NI", "MWIPS"): 100.0,
            ("NI", "PSD"): 0.0,
            ("NI", "Losses"): 0.0,
        },
        node_parameters={
            ("DEAD", "initialLoad"): 0.0,
            ("DEAD", "conformingFactor"): 5.0,
            ("DEAD", "loadIsBad"): 1.0,
            ("LIVE", "initialLoad"): 95.0,
            ("LIVE", "conformingFactor"): 95.0,
            ("OVERRIDE", "initialLoad"): 2.0,
            ("OVERRIDE", "conformingFactor"): 2.0,
            ("OVERRIDE", "loadIsOverride"): 1.0,
        },
        node_market_islands={
            "DEAD": ("NI",),
            "LIVE": ("NI",),
            "OVERRIDE": ("NI",),
        },
        node_electrical_island_sum={
            "DEAD": 0.0,
            "LIVE": 1.0,
            "OVERRIDE": 0.0,
        },
    )

    result = HistoricalFirstLoopLoadReconstructor().reconstruct(case)

    assert result.required_load["DEAD"] > 0.0
    assert set(result.affected_shortfall_mw) == {"DEAD"}


def test_population_selector_emits_only_hash_bound_affected_identity() -> None:
    common = {
        "date_time": "06-NOV-2022 07:00",
        "trading_period": "TP15",
        "use_actual_load": True,
        "island_parameters": {
            ("NI", "MWIPS"): 100.0,
            ("NI", "PSD"): 0.0,
            ("NI", "Losses"): 0.0,
        },
        "node_parameters": {
            ("DEAD", "initialLoad"): 5.0,
            ("DEAD", "conformingFactor"): 5.0,
            ("LIVE", "initialLoad"): 95.0,
            ("LIVE", "conformingFactor"): 95.0,
        },
        "node_market_islands": {"DEAD": ("NI",), "LIVE": ("NI",)},
        "node_electrical_island_sum": {"DEAD": 0.0, "LIVE": 1.0},
    }
    affected = HistoricalFirstLoopCase(
        case_id="affected", shortfall_transfer_enabled=True, **common
    )
    disabled = HistoricalFirstLoopCase(
        case_id="disabled", shortfall_transfer_enabled=False, **common
    )

    records = HistoricalAnalyticPopulationSelector().select(
        (disabled, affected), trading_date="20221106", source_sha256="a" * 64
    )

    assert len(records) == 1
    assert records[0].identity.case_id == "affected"
    assert records[0].identity.source_sha256 == "a" * 64
    assert records[0].affected_shortfall_mw == {"DEAD": 5.0}
