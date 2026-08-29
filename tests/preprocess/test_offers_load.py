from dataclasses import replace

import pytest

from pyspd.contracts import CaseData
from pyspd.data import RawSymbols, ScalarValue
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor


def test_offer_bid_and_required_load_derivations_match_vspd(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor().transform(representative_case)

    assert result.parameter("generation_start").get(("C1", "D1", "O1")) == 60.0
    assert result.set("primary_offer").members == {("C1", "D1", "O1")}
    assert result.set("secondary_offer").members == {("C1", "D1", "O2")}
    assert (
        result.parameter("reserve_maximum_factor").get(("C1", "D1", "O1", "FIR")) == 2.0
    )
    assert result.parameter("ramp_rate_up").get(("C1", "D1", "O1")) == 5.0
    assert ("C1", "D1", "O1", "t1") in result.set("generation_offer_block").members
    assert (
        result.parameter("reserve_offer_percent").get(("C1", "D1", "O1", "t1", "FIR"))
        == 0.25
    )
    assert result.parameter("demand_bid_mw").get(("C1", "D1", "BD1", "t1")) == 30.0
    assert result.parameter("required_load").get(("C1", "D1", "N1")) == 25.0
    assert result.parameter("required_load").get(("C1", "D1", "N2")) == 0.0


def test_constraints_risk_and_scarcity_are_filtered_to_valid_domains(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor().transform(representative_case)

    assert result.set("branch_constraint").members == {("C1", "D1", "BC1")}
    assert result.set("market_node_constraint").members == {("C1", "D1", "MC1")}
    assert result.set("island_risk_group").members == {
        ("C1", "D1", "NI", "RG1", "genRisk")
    }
    assert result.parameter("bad_price_factor").get(("C1", "D1")) == 5.0
    assert result.parameter("scarcity_energy_price_max").get(("C1", "D1")) == 2000.0


def test_rtd_required_load_reconstruction_matches_hand_calculation(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor(
        PreprocessingSettings(
            daily_mode=False,
            apply_rtd_load_reconstruction=True,
        )
    ).transform(representative_case)

    assert result.parameter("target_total_load").get(("C1", "D1", "NI")) == 105.0
    assert result.parameter("estimated_scaling_factor").get(("C1", "D1", "NI")) == 95.0
    assert result.parameter("estimated_initial_load").get(("C1", "D1", "N1")) == 95.0
    assert (
        result.parameter("load_scaling_factor").get(("C1", "D1", "NI")) == 105.0 / 95.0
    )
    assert result.parameter("required_load").get(("C1", "D1", "N1")) == pytest.approx(
        105.0
    )


def test_reserve_model_switch_disables_risk_adjustment(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor(
        PreprocessingSettings(use_reserve_model=False)
    ).transform(representative_case)

    assert all(
        value == 0.0
        for value in result.parameter("risk_adjustment_factor").values.values()
    )


def test_schedule_case_does_not_apply_rtd_load_reconstruction(
    representative_case: CaseData,
) -> None:
    symbols = []
    for symbol in representative_case.symbols.symbols:
        if symbol.name != "i_runMode":
            symbols.append(symbol)
            continue
        records = tuple(
            replace(record, values={"value": ScalarValue.finite(130.0)})
            if record.keys == ("C1", "studyMode")
            else record
            for record in symbol.records
        )
        symbols.append(replace(symbol, records=records))
    schedule = replace(
        representative_case,
        symbols=RawSymbols(
            representative_case.symbols.source_name,
            representative_case.symbols.source_sha256,
            tuple(symbols),
        ),
    )

    result = Vspd506Preprocessor(
        PreprocessingSettings(apply_rtd_load_reconstruction=True)
    ).transform(schedule)
    assert result.parameter("target_total_load").values == {}
    assert result.parameter("required_load").get(("C1", "D1", "N1")) == 25.0
    assert result.parameter("required_load").get(("C1", "D1", "N2")) == 0.0
