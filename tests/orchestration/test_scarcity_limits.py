from __future__ import annotations

from dataclasses import replace

from pyspd.orchestration import DailyCase, PreparedCase, ScheduleType
from pyspd.orchestration.solver import _updated_case
from tests.reserve.conftest import make_reserve_case


def test_shortfall_load_update_does_not_scale_fixed_scarcity_limits() -> None:
    base = make_reserve_case()
    assert base.network is not None
    dynamic = ("C1", "T1", "N1", "t1")
    fixed = ("C1", "T1", "N1", "t2")
    case = replace(
        base,
        scarcity_blocks=frozenset({dynamic, fixed}),
        scarcity_fixed_limit_blocks=frozenset({fixed}),
        scarcity_limit={dynamic: 0.0, fixed: 100.0},
        scarcity_load_factor={dynamic: 2.0, fixed: 0.0},
        scarcity_price={dynamic: 1_000.0, fixed: 1_000.0},
        scarcity_enabled={("C1", "T1"): 1.0},
    )
    specification = DailyCase(
        "C1",
        "T1",
        "TP1",
        130,
        ScheduleType.PRSS,
        30.0,
        300.0,
        0,
        "0" * 64,
    )
    prepared = PreparedCase(
        specification,
        case,
        {("C1", "T1", "N1"): 10.0, ("C1", "T1", "N2"): 30.0},
    )

    updated = _updated_case(prepared)

    assert updated.scarcity_limit[dynamic] == 20.0
    assert updated.scarcity_limit[fixed] == 100.0


def test_dynamic_scarcity_limit_is_zero_for_nonpositive_reconstructed_load() -> None:
    base = make_reserve_case()
    dynamic = ("C1", "T1", "N1", "t1")
    case = replace(
        base,
        scarcity_blocks=frozenset({dynamic}),
        scarcity_limit={dynamic: 0.0},
        scarcity_load_factor={dynamic: 2.0},
        scarcity_price={dynamic: 1_000.0},
        scarcity_enabled={("C1", "T1"): 1.0},
    )
    specification = DailyCase(
        "C1",
        "T1",
        "TP1",
        130,
        ScheduleType.PRSS,
        30.0,
        300.0,
        0,
        "0" * 64,
    )
    prepared = PreparedCase(
        specification,
        case,
        {("C1", "T1", "N1"): -0.1, ("C1", "T1", "N2"): 40.1},
    )

    updated = _updated_case(prepared)

    assert updated.scarcity_limit[dynamic] == 0.0
