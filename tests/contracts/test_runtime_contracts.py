from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pyspd.contracts import (
    CaseData,
    CaseIdentifier,
    ContractError,
    DataResultSchema,
    OperationMode,
    ResultField,
    ResultQuality,
    ResultRecord,
    ResultSet,
    RunConfiguration,
)
from pyspd.data import RawRecord, RawSymbol, RawSymbols, ScalarValue, SymbolType


def test_run_configuration_is_validated_and_deeply_immutable() -> None:
    source_options = {"threads": 1}
    configuration = RunConfiguration(
        "vspd-v5.0.6", OperationMode.SPD, ("C1", "C2"), source_options
    )
    source_options["threads"] = 8

    assert configuration.options == {"threads": 1}
    with pytest.raises(TypeError):
        configuration.options["threads"] = 2  # type: ignore[index]
    with pytest.raises(ContractError, match="duplicate case"):
        RunConfiguration("vspd-v5.0.6", OperationMode.SPD, ("C1", "C1"))
    with pytest.raises(ContractError, match="formulation"):
        RunConfiguration("", OperationMode.SPD, ())


def test_identifiers_and_result_records_are_schema_checked() -> None:
    identifier = CaseIdentifier("C1", "01-NOV-2022 13:00", "TP27")
    assert identifier.case_id == "C1"
    with pytest.raises(ContractError, match="case_id"):
        CaseIdentifier("", "01-NOV-2022 13:00", "TP27")

    schema = DataResultSchema(
        "dispatch",
        "vspd-v5.0.6",
        (
            ResultField("generation", ("offer",), "MW"),
            ResultField("node_price", ("node",), "NZD/MWh"),
        ),
    )
    results = ResultSet(
        schema,
        (
            ResultRecord("generation", ("O1",), 10.0),
            ResultRecord("node_price", ("N1",), None, ResultQuality.UNAVAILABLE),
        ),
    )
    assert len(results.records) == 2
    with pytest.raises(ContractError, match="unknown result field"):
        ResultSet(schema, (ResultRecord("reserve", ("O1",), 1.0),))
    with pytest.raises(ContractError, match="key dimension"):
        ResultSet(schema, (ResultRecord("generation", ("O1", "extra"), 1.0),))
    with pytest.raises(ContractError, match="duplicate result field"):
        DataResultSchema(
            "bad",
            "vspd-v5.0.6",
            (ResultField("x", (), "MW"), ResultField("x", (), "MW")),
        )


def test_result_contracts_are_frozen() -> None:
    field = ResultField("objective", (), "NZD")
    with pytest.raises(FrozenInstanceError):
        field.unit = "MW"  # type: ignore[misc]


def test_case_data_rejects_unselected_or_unknown_case_records() -> None:
    definitions = RawSymbol(
        "i_caseDefn",
        SymbolType.SET,
        3,
        ("ca", "cn", "rundt"),
        "cases",
        (("C1",), ("case",), ("run",)),
        (
            RawRecord(
                ("C1", "case", "run"),
                {"element_text": ScalarValue.text("")},
            ),
        ),
    )
    quantity = RawSymbol(
        "quantity",
        SymbolType.PARAMETER,
        2,
        ("ca", "node"),
        "quantity",
        (("C1",), ("N1",)),
        (RawRecord(("C1", "N1"), {"value": ScalarValue.finite(1.0)}),),
    )
    symbols = RawSymbols("case.gdx", "a" * 64, (definitions, quantity))
    identifier = CaseIdentifier("C1", "01-NOV-2022 13:00", "TP27")

    assert CaseData("vspd-v5.0.6", identifier, symbols).identifier == identifier
    with pytest.raises(ContractError, match="absent from i_caseDefn"):
        CaseData(
            "vspd-v5.0.6",
            CaseIdentifier("C2", "01-NOV-2022 13:00", "TP27"),
            symbols,
        )
