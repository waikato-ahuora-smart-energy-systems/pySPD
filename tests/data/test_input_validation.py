from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyspd.data import (
    InputValidationError,
    RawRecord,
    RawSymbol,
    RawSymbols,
    ScalarValue,
    SymbolCatalog,
    V5InputValidator,
)


def record(keys: tuple[str, ...], value: float | None = None) -> RawRecord:
    return RawRecord(
        keys,
        {"value": ScalarValue.finite(value)} if value is not None else {},
    )


def valid_source() -> RawSymbols:
    catalog = SymbolCatalog.vspd_v5()
    symbols: dict[str, RawSymbol] = {
        spec.name: RawSymbol(
            spec.name,
            spec.symbol_type,
            spec.dimension,
            spec.domains,
            "validation fixture",
            tuple(() for _ in range(spec.dimension)),
            (),
        )
        for spec in catalog.symbols
    }

    def set_records(
        name: str,
        records: tuple[RawRecord, ...],
        uels: tuple[tuple[str, ...], ...],
    ) -> None:
        symbols[name] = replace(symbols[name], records=records, uel_orders=uels)

    set_records(
        "i_caseDefn",
        (RawRecord(("C1", "case", "run"), {"element_text": ScalarValue.text("")}),),
        (("C1",), ("case",), ("run",)),
    )
    set_records(
        "i_dateTimeTradePeriodMap",
        (RawRecord(("C1", "D1", "TP1"), {"element_text": ScalarValue.text("")}),),
        (("C1",), ("D1",), ("TP1",)),
    )
    set_records(
        "i_node",
        (
            RawRecord(("N1",), {"element_text": ScalarValue.text("")}),
            RawRecord(("N2",), {"element_text": ScalarValue.text("")}),
        ),
        (("N1", "N2"),),
    )
    set_records(
        "i_bus",
        (
            RawRecord(("B1",), {"element_text": ScalarValue.text("")}),
            RawRecord(("B2",), {"element_text": ScalarValue.text("")}),
        ),
        (("B1", "B2"),),
    )
    mapping = (
        RawRecord(("C1", "D1", "N1", "B1"), {"element_text": ScalarValue.text("")}),
        RawRecord(("C1", "D1", "N1", "B2"), {"element_text": ScalarValue.text("")}),
    )
    set_records(
        "i_dateTimeNodeBus",
        mapping,
        (("C1",), ("D1",), ("N1", "N2"), ("B1", "B2")),
    )
    set_records(
        "i_dateTimeNodeBusAllocationFactor",
        (
            record(("C1", "D1", "N1", "B1"), 0.4),
            record(("C1", "D1", "N1", "B2"), 0.6),
        ),
        (("C1",), ("D1",), ("N1", "N2"), ("B1", "B2")),
    )
    set_records(
        "i_dateTimeEnergyOffer",
        (
            record(("C1", "D1", "O1", "1", "limitMW"), 10.0),
            record(("C1", "D1", "O1", "1", "price"), 50.0),
            record(("C1", "D1", "O1", "2", "limitMW"), 5.0),
            record(("C1", "D1", "O1", "2", "price"), 60.0),
        ),
        (("C1",), ("D1",), ("O1",), ("1", "2"), ("limitMW", "price")),
    )
    return RawSymbols("valid.gdx", "a" * 64, tuple(symbols.values()))


def replace_symbol(raw: RawSymbols, replacement: RawSymbol) -> RawSymbols:
    return replace(
        raw,
        symbols=tuple(
            replacement if symbol.name == replacement.name else symbol
            for symbol in raw.symbols
        ),
    )


def test_valid_input_passes_all_pre_model_checks() -> None:
    report = V5InputValidator().validate(valid_source())
    assert report.passed
    report.raise_for_errors()


@given(st.floats(min_value=0.01, max_value=0.5, allow_nan=False))
def test_allocation_totals_fail_with_actionable_identity(delta: float) -> None:
    raw = valid_source()
    allocation = raw["i_dateTimeNodeBusAllocationFactor"]
    bad = replace(
        allocation,
        records=(allocation.records[0], record(("C1", "D1", "N1", "B2"), 0.6 + delta)),
    )

    with pytest.raises(InputValidationError, match="allocation_sum.*C1.*D1.*N1"):
        V5InputValidator().validate(replace_symbol(raw, bad)).raise_for_errors()


def test_unknown_domains_and_curve_order_fail_before_model_construction() -> None:
    raw = valid_source()
    node_bus = raw["i_dateTimeNodeBus"]
    unknown = replace(
        node_bus,
        records=(
            RawRecord(
                ("C1", "D1", "N9", "B1"),
                {"element_text": ScalarValue.text("")},
            ),
        ),
        uel_orders=(("C1",), ("D1",), ("N1", "N2", "N9"), ("B1", "B2")),
    )
    with pytest.raises(InputValidationError, match="unknown_node.*N9"):
        V5InputValidator().validate(replace_symbol(raw, unknown)).raise_for_errors()

    curve = raw["i_dateTimeEnergyOffer"]
    out_of_order = replace(curve, records=(curve.records[2], curve.records[0]))
    with pytest.raises(InputValidationError, match="curve_order"):
        V5InputValidator().validate(replace_symbol(raw, out_of_order)).raise_for_errors()


def test_bid_schedule_datetimes_are_permitted_but_unknown_cases_are_not() -> None:
    raw = valid_source()
    bid_node = replace(
        raw["i_dateTimeBidNode"],
        records=(
            RawRecord(
                ("C1", "AUXILIARY-DT", "BD1", "N1"),
                {"element_text": ScalarValue.text("")},
            ),
        ),
        uel_orders=(("C1",), ("AUXILIARY-DT",), ("BD1",), ("N1",)),
    )
    assert V5InputValidator().validate(replace_symbol(raw, bid_node)).passed

    node_parameter = replace(
        raw["i_dateTimeNodeParameter"],
        records=(record(("C2", "D1", "N1", "demand"), 1.0),),
        uel_orders=(("C1", "C2"), ("D1",), ("N1",), ("demand",)),
    )
    with pytest.raises(InputValidationError, match="unknown_case_datetime.*C2"):
        V5InputValidator().validate(
            replace_symbol(raw, node_parameter)
        ).raise_for_errors()
