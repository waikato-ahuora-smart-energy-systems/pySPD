"""Probity-first public contract for Gate 8 orchestration."""

from __future__ import annotations

import pytest

from pyspd.orchestration import (
    CaseRunStatus,
    DailyCase,
    DailyRunConfiguration,
    DailyRunner,
    DailyRunState,
    MarketPricePostProcessor,
    OrchestrationError,
    OverrideFamily,
    OverrideScope,
    RunEventKind,
    ScheduleType,
    ShortfallLoop,
)


def test_gate8_public_contract_is_class_based_and_bounded() -> None:
    assert DailyRunner
    assert MarketPricePostProcessor
    assert ShortfallLoop
    assert set(OverrideFamily) == {
        OverrideFamily.DEMAND,
        OverrideFamily.OFFER_PARAMETER,
        OverrideFamily.ENERGY_OFFER,
        OverrideFamily.RESERVE_OFFER,
        OverrideFamily.BID_PARAMETER,
        OverrideFamily.ENERGY_BID,
        OverrideFamily.BRANCH_PARAMETER,
        OverrideFamily.BRANCH_CONSTRAINT_RHS,
        OverrideFamily.BRANCH_CONSTRAINT_FACTOR,
        OverrideFamily.MARKET_NODE_CONSTRAINT_RHS,
        OverrideFamily.MARKET_NODE_CONSTRAINT_FACTOR,
    }
    assert tuple(OverrideScope) == (
        OverrideScope.ALL_TIME,
        OverrideScope.TRADING_PERIOD,
        OverrideScope.DATE_TIME,
        OverrideScope.CASE_ID,
    )
    assert CaseRunStatus.COMPLETE.value == "complete"
    assert DailyRunState.INTERRUPTED.value == "interrupted"
    assert RunEventKind.PRICES_PUBLISHED.value == "prices_published"
    configuration = DailyRunConfiguration(
        formulation_id="vspd-v5.0.6-reserve",
        source_sha256="0" * 64,
        maximum_solve_loops=5,
    )
    assert configuration.maximum_solve_loops == 5

    selected = DailyRunConfiguration(
        formulation_id="vspd-v5.0.6-reserve",
        source_sha256="0" * 64,
        maximum_solve_loops=5,
        application_configuration_sha256="1" * 64,
    )
    assert selected.logical_sha256 != configuration.logical_sha256


def test_case_contract_rejects_incompatible_study_mode_and_schedule() -> None:
    with pytest.raises(
        OrchestrationError,
        match="REQ-G8-ORCHESTRATION: incompatible study mode and schedule type",
    ):
        DailyCase(
            "C1",
            "01-JAN-2024 00:00",
            "TP1",
            101,
            ScheduleType.PRSS,
            5.0,
            300.0,
            0,
            "0" * 64,
        )
