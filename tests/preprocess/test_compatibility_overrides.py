from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from pyspd.contracts import CaseData
from pyspd.preprocess import (
    OverrideMethod,
    OverrideOperation,
    Vspd506Preprocessor,
    apply_overrides,
    apply_overrides_with_provenance,
)


def test_date_compatibility_boundaries_are_materialized(
    case_factory: Callable[[date], CaseData],
) -> None:
    old = Vspd506Preprocessor().transform(case_factory(date(2023, 4, 27)))
    new = Vspd506Preprocessor().transform(case_factory(date(2023, 4, 28)))
    directional = Vspd506Preprocessor().transform(case_factory(date(2025, 3, 17)))

    assert old.parameter("spd_loss_tolerance").get(()) == 0.005
    assert old.parameter("legacy_prss_shared_nfr").get(()) == 1.0
    assert new.parameter("spd_loss_tolerance").get(()) == 0.00005
    assert new.parameter("legacy_prss_shared_nfr").get(()) == 0.0
    assert directional.parameter("directional_risk_available").get(()) == 1.0


@pytest.mark.parametrize(
    ("input_date", "legacy", "fir_transition", "directional"),
    [
        (date(2019, 3, 27), 1.0, 0.0, 0.0),
        (date(2019, 3, 28), 1.0, 1.0, 0.0),
        (date(2019, 3, 29), 1.0, 1.0, 0.0),
        (date(2023, 4, 26), 1.0, 1.0, 0.0),
        (date(2023, 4, 27), 1.0, 1.0, 0.0),
        (date(2023, 4, 28), 0.0, 1.0, 0.0),
        (date(2025, 3, 16), 0.0, 1.0, 0.0),
        (date(2025, 3, 17), 0.0, 1.0, 1.0),
        (date(2025, 3, 18), 0.0, 1.0, 1.0),
    ],
)
def test_every_compatibility_boundary_has_before_on_after_cases(
    case_factory: Callable[[date], CaseData],
    input_date: date,
    legacy: float,
    fir_transition: float,
    directional: float,
) -> None:
    result = Vspd506Preprocessor().transform(case_factory(input_date))

    assert result.parameter("legacy_prss_shared_nfr").get(()) == legacy
    assert result.parameter("fir_uses_bipole_transition").get(()) == fir_transition
    assert result.parameter("directional_risk_available").get(()) == directional


def test_override_order_is_scale_then_increment_then_value() -> None:
    values = {("C1", "D1", "N1"): 10.0, ("C1", "D1", "N2"): 20.0}
    operations = (
        OverrideOperation(
            "required_load", ("C1", "D1", None), OverrideMethod.VALUE, 7.0, 30
        ),
        OverrideOperation(
            "required_load", ("C1", "D1", None), OverrideMethod.SCALE, 2.0, 10
        ),
        OverrideOperation(
            "required_load", ("C1", "D1", None), OverrideMethod.INCREMENT, 3.0, 20
        ),
    )

    assert apply_overrides("required_load", values, operations) == {
        ("C1", "D1", "N1"): 7.0,
        ("C1", "D1", "N2"): 7.0,
    }
    assert values[("C1", "D1", "N1")] == 10.0

    governed = apply_overrides_with_provenance("required_load", values, operations)
    assert [record.method for record in governed.provenance[:3]] == [
        OverrideMethod.SCALE,
        OverrideMethod.SCALE,
        OverrideMethod.INCREMENT,
    ]
    assert governed.provenance[-1].after == 7.0
    assert governed.provenance[-1].precedence == 30
