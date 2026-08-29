from __future__ import annotations

import pyomo.environ as pyo
import pytest

from pyspd.architecture import ModelAssembler
from pyspd.core_energy import CoreEnergySolvePolicy, core_energy_formulation
from tests.core_energy.conftest import make_core_case


def _solve(data):
    built = ModelAssembler().assemble(core_energy_formulation(), data)
    CoreEnergySolvePolicy().solve(built)
    return built


def test_generation_start_ramp_up_causes_balance_deficit() -> None:
    built = _solve(
        make_core_case(
            load=60.0,
            offers=(("GEN", 100.0, 10.0),),
            starts={"GEN": 40.0},
            ramp_up={"GEN": 20.0},
            ramp_down={"GEN": 20.0},
            study_mode=101.0,
        )
    )
    assert pyo.value(built.artifacts["generation"]["C1", "T1", "GEN"]) == pytest.approx(
        50.0
    )
    assert pyo.value(
        built.artifacts["balance_deficit"]["C1", "T1", "NI"]
    ) == pytest.approx(10.0)
    assert pyo.value(built.artifacts["ramp_deficit"]["C1", "T1", "GEN"]) == 0.0


def test_generation_start_ramp_down_causes_balance_surplus() -> None:
    built = _solve(
        make_core_case(
            load=40.0,
            offers=(("GEN", 100.0, 10.0),),
            starts={"GEN": 60.0},
            ramp_up={"GEN": 20.0},
            ramp_down={"GEN": 20.0},
            study_mode=201.0,
        )
    )
    assert pyo.value(built.artifacts["generation"]["C1", "T1", "GEN"]) == pytest.approx(
        50.0
    )
    assert pyo.value(
        built.artifacts["balance_surplus"]["C1", "T1", "NI"]
    ) == pytest.approx(10.0)


def test_explicit_ramp_slack_restores_feasibility_when_cap_conflicts() -> None:
    built = _solve(
        make_core_case(
            load=30.0,
            offers=(("GEN", 100.0, 10.0),),
            starts={"GEN": 60.0},
            ramp_down={"GEN": 20.0},
            generation_maximum={"GEN": 30.0},
            study_mode=101.0,
        )
    )
    assert pyo.value(built.artifacts["ramp_surplus"]["C1", "T1", "GEN"]) == pytest.approx(
        20.0
    )
    assert pyo.value(built.artifacts["balance_deficit"]["C1", "T1", "NI"]) == 0.0
    assert pyo.value(built.artifacts["balance_surplus"]["C1", "T1", "NI"]) == 0.0
