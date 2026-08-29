"""Gate 12 native-SOS qualification profile contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pyomo.environ as pyo

from pyspd.architecture import ModelAssembler
from pyspd.hvdc.data import SosRepresentation
from pyspd.v16.data import Spd16Case
from pyspd.v16.formulation import spd16_formulation
from tests.reserve.conftest import make_reserve_case


def test_v16_native_sos_profile_covers_network_and_reserve_curves() -> None:
    case = Spd16Case.from_reserve_case(
        make_reserve_case(), source_date=date(2026, 6, 23)
    )
    assert case.hvdc is not None
    case = replace(
        case,
        hvdc=replace(
            case.hvdc,
            enforce_sos2=True,
            sos_representation=SosRepresentation.NATIVE,
        ),
    )

    built = ModelAssembler().assemble(spd16_formulation(), case)

    assert tuple(built.model.component_data_objects(pyo.SOSConstraint, active=True))
    assert all(
        variable.fixed and not variable.is_binary()
        for artifact in (
            "lambda_hvdc_energy_interval",
            "lambda_hvdc_reserve_interval",
        )
        for variable in built.artifacts[artifact].values()
    )
