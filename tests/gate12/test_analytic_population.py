"""Probity tests for algebraic historical shortfall enumeration."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.gate12.analytic_population import (
    HistoricalAnalyticDayEnumerator,
    HistoricalAnalyticPopulationEvidenceBuilder,
    HistoricalAnalyticPopulationSelector,
    HistoricalFirstLoopCase,
    HistoricalFirstLoopLoadReconstructor,
)
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.historical_population import (
    HistoricalInputArtifact,
    HistoricalInputInventory,
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


def test_day_enumerator_verifies_source_before_loading(tmp_path: Path) -> None:
    source = tmp_path / "Pricing_20221106.gdx"
    source.write_bytes(b"canonical-gdx")
    artifact = HistoricalInputArtifact(
        trading_date="20221106",
        size_bytes=source.stat().st_size,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )

    class Loader:
        calls = 0

        def load(
            self, path: Path, system_directory: Path
        ) -> tuple[HistoricalFirstLoopCase, ...]:
            self.calls += 1
            assert path == source
            return ()

    loader = Loader()
    result = HistoricalAnalyticDayEnumerator(loader=loader).enumerate(
        artifact=artifact,
        path=source,
        system_directory=tmp_path,
    )
    assert result.source_sha256 == artifact.sha256
    assert loader.calls == 1

    source.write_bytes(b"tampered")
    with pytest.raises(EvidenceContractError, match="source size or hash"):
        HistoricalAnalyticDayEnumerator(loader=loader).enumerate(
            artifact=artifact,
            path=source,
            system_directory=tmp_path,
        )
    assert loader.calls == 1


def test_population_builder_rejects_incomplete_declared_population() -> None:
    inventory = HistoricalInputInventory(
        (HistoricalInputArtifact("20221106", 1, "a" * 64),)
    )

    with pytest.raises(EvidenceContractError, match="exactly 139 daily results"):
        HistoricalAnalyticPopulationEvidenceBuilder().build(
            daily_results=(), inventory=inventory
        )
