from __future__ import annotations

from dataclasses import replace

import pytest

from pyspd.contracts import CaseData
from pyspd.data import RawRecord, RawSymbol, RawSymbols, ScalarValue, SymbolType
from pyspd.orchestration import (
    DailyCaseDataIndex,
    DailyCasePreparer,
    DailyCaseSelector,
    OverrideApplier,
    OverrideFamily,
    OverrideInstruction,
    OverrideScope,
    ScheduleType,
)
from pyspd.orchestration.types import OrchestrationError
from pyspd.preprocess.input import CaseInput
from tests.preprocess.conftest import make_case


def _with_publication(case: CaseData, seconds: float = 300.0) -> CaseData:
    symbol = RawSymbol(
        "i_priceCaseFilesPublishedSecs",
        SymbolType.PARAMETER,
        2,
        ("ca", "tp"),
        "publication seconds",
        (("C1",), ("1",)),
        (RawRecord(("C1", "1"), {"value": ScalarValue.finite(seconds)}),),
    )
    symbols = RawSymbols(
        case.symbols.source_name,
        case.symbols.source_sha256,
        (*case.symbols.symbols, symbol),
    )
    return replace(case, symbols=symbols)


def _with_empty_node_transfer(case: CaseData) -> CaseData:
    symbol = RawSymbol(
        "i_dateTimeNodetoNode",
        SymbolType.SET,
        4,
        ("ca", "dt", "n", "n1"),
        "node transfer map",
        ((), (), (), ()),
        (),
    )
    return replace(
        case,
        symbols=RawSymbols(
            case.symbols.source_name,
            case.symbols.source_sha256,
            (*case.symbols.symbols, symbol),
        ),
    )


def _with_shortfall_transfer(case: CaseData) -> CaseData:
    symbols = []
    for symbol in case.symbols.symbols:
        if symbol.name != "i_dateTimeParameter":
            symbols.append(symbol)
            continue
        symbols.append(
            RawSymbol(
                symbol.name,
                symbol.symbol_type,
                symbol.dimension,
                symbol.domains,
                symbol.description,
                symbol.uel_orders,
                (
                    *symbol.records,
                    RawRecord(
                        ("C1", "D1", "enrgShortfallTransfer"),
                        {"value": ScalarValue.finite(1.0)},
                    ),
                ),
            )
        )
    return replace(
        case,
        symbols=RawSymbols(
            case.symbols.source_name,
            case.symbols.source_sha256,
            tuple(symbols),
        ),
    )


def _with_study_mode(case: CaseData, study_mode: int) -> CaseData:
    symbols = []
    for symbol in case.symbols.symbols:
        if symbol.name != "i_runMode":
            symbols.append(symbol)
            continue
        records = tuple(
            RawRecord(record.keys, {"value": ScalarValue.finite(study_mode)})
            if record.keys == ("C1", "studyMode")
            else record
            for record in symbol.records
        )
        symbols.append(
            RawSymbol(
                symbol.name,
                symbol.symbol_type,
                symbol.dimension,
                symbol.domains,
                symbol.description,
                symbol.uel_orders,
                records,
            )
        )
    return replace(
        case,
        symbols=RawSymbols(
            case.symbols.source_name,
            case.symbols.source_sha256,
            tuple(symbols),
        ),
    )


def test_daily_selector_preserves_source_order_and_filters_zero_duration() -> None:
    case = _with_publication(make_case())
    selected = DailyCaseSelector().select(
        case.symbols,
        schedule_types=(ScheduleType.RTD,),
        publication_only=True,
    )
    assert [
        (item.case_id, item.trading_period, item.publication_seconds)
        for item in selected
    ] == [("C1", "1", 300.0)]
    zero = _with_publication(make_case(), 0.0)
    assert DailyCaseSelector().select(zero.symbols, publication_only=True) == ()


def test_daily_selector_rejects_requested_case_missing_from_source() -> None:
    case = _with_publication(make_case())

    try:
        DailyCaseSelector().select(case.symbols, case_ids=("MISSING",))
    except OrchestrationError as error:
        assert "requested case IDs" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("missing requested case was silently ignored")


def test_case_selector_isolates_every_case_scoped_symbol() -> None:
    case = _with_publication(make_case())
    selected = DailyCaseSelector().select(case.symbols)[0]
    isolated = DailyCaseSelector().case_data(case.symbols, selected)
    assert isolated.identifier.case_id == "C1"
    assert all(
        record.keys[0] == "C1"
        for symbol in isolated.symbols.symbols
        if symbol.domains and symbol.domains[0] == "ca"
        for record in symbol.records
    )


def test_case_data_index_matches_scan_with_noncontiguous_case_records() -> None:
    case = _with_publication(make_case())
    source = case.symbols["i_dateTimeParameter"]
    interleaved = RawSymbol(
        source.name,
        source.symbol_type,
        source.dimension,
        source.domains,
        source.description,
        source.uel_orders,
        (
            RawRecord(
                ("C2", "D2", "studyMode"),
                {"value": ScalarValue.finite(101.0)},
            ),
            *source.records,
            RawRecord(
                ("C2", "D2", "maxSolveLoop"),
                {"value": ScalarValue.finite(5.0)},
            ),
        ),
    )
    symbols = RawSymbols(
        case.symbols.source_name,
        case.symbols.source_sha256,
        tuple(
            interleaved if symbol.name == source.name else symbol
            for symbol in case.symbols.symbols
        ),
    )
    selector = DailyCaseSelector()
    selected = selector.select(symbols)[0]

    indexed = DailyCaseDataIndex(symbols, case_ids=(selected.case_id,)).case_data(
        selected
    )
    scanned = selector.case_data(symbols, selected)

    assert indexed == scanned
    assert indexed.symbols["i_dateTimeParameter"].records == source.records


def test_case_data_index_rejects_case_outside_its_declared_scope() -> None:
    case = _with_publication(make_case())
    selected = DailyCaseSelector().select(case.symbols)[0]
    index = DailyCaseDataIndex(case.symbols, case_ids=("C2",))

    with pytest.raises(OrchestrationError, match="not present in case-data index"):
        index.case_data(selected)


def test_daily_preparer_keeps_source_demand_for_rtd_daily_mode() -> None:
    case = _with_empty_node_transfer(_with_publication(make_case()))
    selector = DailyCaseSelector()
    selected = selector.select(case.symbols)[0]

    prepared = DailyCasePreparer().prepare(
        selector.case_data(case.symbols, selected),
        selected,
        daily_mode=True,
    )

    # Pinned vSPD guards its RTD load reconstruction with dailymode = 0.
    assert prepared.required_load[("C1", "D1", "N1")] == 25.0
    assert prepared.required_load[("C1", "D1", "N2")] == 0.0
    assert not prepared.rtd_load_reconstruction_enabled


@pytest.mark.parametrize(
    ("study_mode", "daily_transfer_enabled"),
    ((101, False), (201, False), (130, True)),
)
def test_daily_preparer_matches_vspd_shortfall_transfer_guard(
    study_mode: int, daily_transfer_enabled: bool
) -> None:
    case = _with_study_mode(
        _with_shortfall_transfer(
            _with_empty_node_transfer(_with_publication(make_case()))
        ),
        study_mode,
    )
    selector = DailyCaseSelector()
    selected = selector.select(case.symbols)[0]
    isolated = selector.case_data(case.symbols, selected)

    daily = DailyCasePreparer().prepare(isolated, selected, daily_mode=True)
    non_daily = DailyCasePreparer().prepare(isolated, selected, daily_mode=False)

    assert selected.study_mode == study_mode
    assert daily.transfer_enabled is daily_transfer_enabled
    assert non_daily.transfer_enabled


def test_all_override_families_apply_and_are_audited() -> None:
    case = make_case()
    instructions = (
        OverrideInstruction(
            OverrideFamily.DEMAND,
            OverrideScope.ALL_TIME,
            "All",
            ("NODE", "N1", "ALL", "SCALE"),
            2.0,
        ),
        OverrideInstruction(
            OverrideFamily.OFFER_PARAMETER,
            OverrideScope.ALL_TIME,
            "All",
            ("O1", "rampUpRate"),
            7.0,
        ),
        OverrideInstruction(
            OverrideFamily.ENERGY_OFFER,
            OverrideScope.ALL_TIME,
            "All",
            ("O1", "price", "t1"),
            8.0,
        ),
        OverrideInstruction(
            OverrideFamily.RESERVE_OFFER,
            OverrideScope.ALL_TIME,
            "All",
            ("O1", "FIR", "PLRO", "price", "t1"),
            9.0,
        ),
        OverrideInstruction(
            OverrideFamily.BID_PARAMETER,
            OverrideScope.ALL_TIME,
            "All",
            ("B1", "dispatchable"),
            1.0,
        ),
        OverrideInstruction(
            OverrideFamily.ENERGY_BID,
            OverrideScope.ALL_TIME,
            "All",
            ("B1", "price", "t1"),
            11.0,
        ),
        OverrideInstruction(
            OverrideFamily.BRANCH_PARAMETER,
            OverrideScope.ALL_TIME,
            "All",
            ("BR1", "forwardCap"),
            12.0,
        ),
        OverrideInstruction(
            OverrideFamily.BRANCH_CONSTRAINT_RHS,
            OverrideScope.ALL_TIME,
            "All",
            ("BC1", "cnstrLimit"),
            13.0,
        ),
        OverrideInstruction(
            OverrideFamily.BRANCH_CONSTRAINT_FACTOR,
            OverrideScope.ALL_TIME,
            "All",
            ("BC1", "BR1"),
            14.0,
        ),
        OverrideInstruction(
            OverrideFamily.MARKET_NODE_CONSTRAINT_RHS,
            OverrideScope.ALL_TIME,
            "All",
            ("MC1", "cnstrLimit"),
            15.0,
        ),
        OverrideInstruction(
            OverrideFamily.MARKET_NODE_CONSTRAINT_FACTOR,
            OverrideScope.ALL_TIME,
            "All",
            ("MC1", "O1", "NA", "NA"),
            16.0,
        ),
    )
    output, audit = OverrideApplier().apply(case, instructions)
    source = CaseInput(output)
    assert {entry.family for entry in audit.entries} == set(OverrideFamily)
    assert (
        source.component("i_dateTimeNodeParameter", "demand")[("C1", "D1", "N1")]
        == 50.0
    )
    assert (
        source.numeric("i_dateTimeOfferParameter")[("C1", "D1", "O1", "rampUpRate")]
        == 7.0
    )
    assert (
        source.numeric("i_dateTimeEnergyOffer")[("C1", "D1", "O1", "t1", "price")]
        == 8.0
    )
    assert (
        source.numeric("i_dateTimeReserveOffer")[
            ("C1", "D1", "O1", "FIR", "PLRO", "t1", "price")
        ]
        == 9.0
    )
    assert audit.input_logical_sha256 != audit.output_logical_sha256


def test_override_scope_precedence_ends_with_case_id_and_supports_zero() -> None:
    case = make_case()
    target = ("O1", "rampUpRate")
    instructions = (
        OverrideInstruction(
            OverrideFamily.OFFER_PARAMETER, OverrideScope.CASE_ID, "C1", target, 0.0
        ),
        OverrideInstruction(
            OverrideFamily.OFFER_PARAMETER, OverrideScope.DATE_TIME, "D1", target, 3.0
        ),
        OverrideInstruction(
            OverrideFamily.OFFER_PARAMETER,
            OverrideScope.TRADING_PERIOD,
            "1",
            target,
            2.0,
        ),
        OverrideInstruction(
            OverrideFamily.OFFER_PARAMETER, OverrideScope.ALL_TIME, "All", target, 1.0
        ),
    )
    output, audit = OverrideApplier().apply(case, instructions)
    value = CaseInput(output).numeric("i_dateTimeOfferParameter")[
        ("C1", "D1", "O1", "rampUpRate")
    ]
    assert value == 0.0
    assert [entry.after for entry in audit.entries] == [1.0, 2.0, 3.0, 0.0]
