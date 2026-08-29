from dataclasses import replace

import pytest

from pyspd.contracts import CaseData
from pyspd.data import RawSymbols, ScalarValue
from pyspd.preprocess import PreprocessingSettings, Vspd506Preprocessor
from pyspd.preprocess.losses import (
    LOSS_COEFFICIENT_A,
    LOSS_COEFFICIENT_C,
    MAX_FLOW_SEGMENT,
    _loss_points,
)


def test_loss_curve_derivations_match_vspd_breakpoints(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor().transform(representative_case)
    points = result.parameter("loss_segment_mw")
    factors = result.parameter("loss_segment_factor")

    assert points.get(("C1", "D1", "BR1", "ls1", "forward")) == pytest.approx(
        LOSS_COEFFICIENT_A * 100.0
    )
    assert points.get(("C1", "D1", "BR1", "ls2", "forward")) == pytest.approx(
        (1.0 - LOSS_COEFFICIENT_A) * 100.0
    )
    assert points.get(("C1", "D1", "BR1", "ls3", "forward")) == MAX_FLOW_SEGMENT
    assert factors.get(("C1", "D1", "BR1", "ls2", "forward")) == pytest.approx(
        0.01 * 0.02 * 100.0
    )
    assert result.parameter("branch_fixed_loss").get(("C1", "D1", "BR1")) == 1.0

    valid = result.set("valid_loss_segment").members
    assert ("C1", "D1", "HV1", "ls2", "forward") in valid
    assert (
        result.parameter("hvdc_breakpoint_flow").get(
            ("C1", "D1", "HV1", "ls2", "forward")
        )
        == MAX_FLOW_SEGMENT
    )
    assert (
        result.parameter("hvdc_breakpoint_flow").get(
            ("C1", "D1", "HV1", "ls2", "backward")
        )
        == 0.0
    )


def test_six_tranche_branch_curve_matches_vspd_coefficients() -> None:
    points, factors = _loss_points(6, 100.0, 0.02)

    assert points[0] == LOSS_COEFFICIENT_C * 100.0
    assert points[2] == 50.0
    assert points[5] == MAX_FLOW_SEGMENT
    assert factors[0] == pytest.approx(0.01 * 0.75 * LOSS_COEFFICIENT_C * 0.02 * 100.0)


def test_loss_model_switches_zero_resistance_and_fixed_loss(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor(
        PreprocessingSettings(use_ac_loss_model=False, use_hvdc_loss_model=False)
    ).transform(representative_case)

    assert all(
        value == 0.0 for value in result.parameter("branch_resistance").values.values()
    )
    assert all(
        value == 0.0 for value in result.parameter("branch_fixed_loss").values.values()
    )
    assert all(
        value == 0.0
        for value in result.parameter("loss_segment_factor").values.values()
    )


def test_unsupported_loss_tranche_count_fails_before_model_build(
    representative_case: CaseData,
) -> None:
    symbols = []
    for symbol in representative_case.symbols.symbols:
        if symbol.name != "i_dateTimeBranchParameter":
            symbols.append(symbol)
            continue
        records = tuple(
            replace(record, values={"value": ScalarValue.finite(2.0)})
            if record.keys == ("C1", "D1", "BR1", "numLossTranches")
            else record
            for record in symbol.records
        )
        symbols.append(replace(symbol, records=records))
    invalid = replace(
        representative_case,
        symbols=RawSymbols(
            representative_case.symbols.source_name,
            representative_case.symbols.source_sha256,
            tuple(symbols),
        ),
    )

    with pytest.raises(ValueError, match="unsupported branch loss tranche count"):
        Vspd506Preprocessor().transform(invalid)
