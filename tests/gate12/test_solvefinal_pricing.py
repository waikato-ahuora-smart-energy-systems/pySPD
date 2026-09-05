"""Gate 12 contracts for GAMS solveFinal-compatible RMIP state."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest

from pyspd.architecture import ModelAssembler
from pyspd.hvdc import formulation as hvdc_formulation_module
from pyspd.hvdc.data import SosRepresentation
from pyspd.orchestration import DailyCase, PreparedCase, ScheduleType
from pyspd.orchestration.solver import _updated_case
from pyspd.reserve import ReserveSolvePolicy, reserve_formulation
from pyspd.solver import SolverExecutionError
from tests.reserve.conftest import make_reserve_case


def test_application_solve_uses_native_scip_sos_state() -> None:
    case = make_reserve_case()
    assert case.network is not None
    assert case.hvdc is not None
    ca, date_time = next(iter(case.periods))
    prepared = PreparedCase(
        DailyCase(
            ca,
            date_time,
            "TP1",
            101,
            ScheduleType.RTD,
            5.0,
            300.0,
            0,
            "0" * 64,
        ),
        case,
        case.network.node_load,
    )

    updated = _updated_case(prepared)

    assert updated.hvdc is not None
    assert updated.hvdc.sos_representation is SosRepresentation.NATIVE


def test_pricing_preserves_native_sos_support_and_reoptimises_active_weights() -> None:
    built = ModelAssembler().assemble(reserve_formulation(), make_reserve_case())
    outcome = ReserveSolvePolicy().solve(built)

    expected_names = {
        variable.name
        for artifact in (
            "hvdc_lambda",
            "lambda_hvdc_energy",
            "lambda_hvdc_reserve",
        )
        for variable in built.artifacts[artifact].values()
    }
    assert set(outcome.fixed_sos_members) == expected_names
    assert expected_names
    for artifact in ("lambda_hvdc_energy", "lambda_hvdc_reserve"):
        primary = outcome.primary_model.artifacts[artifact]
        pricing = outcome.pricing_model.artifacts[artifact]
        for key in primary:
            name = primary[key].name
            assert pyo.value(primary[key]) == pytest.approx(
                outcome.fixed_sos_members[name]
            )
            if outcome.fixed_sos_members[name] == 0.0:
                assert pricing[key].fixed
                assert pyo.value(pricing[key]) == 0.0
            else:
                assert not pricing[key].fixed


def test_sos_member_fixing_is_separate_from_binary_fix_map() -> None:
    built = ModelAssembler().assemble(reserve_formulation(), make_reserve_case())
    outcome = ReserveSolvePolicy().solve(built)

    assert set(outcome.fixed_sos_members).isdisjoint(outcome.fixed_discrete)
    assert all(
        not variable.is_binary() and not variable.is_integer()
        for artifact in ("lambda_hvdc_energy", "lambda_hvdc_reserve")
        for variable in outcome.primary_model.artifacts[artifact].values()
    )


def test_native_pricing_records_objective_guarded_sos_support_polishing() -> None:
    case = make_reserve_case()
    assert case.hvdc is not None
    case = replace(
        case,
        hvdc=replace(
            case.hvdc,
            sos_representation=SosRepresentation.NATIVE,
        ),
    )
    built = ModelAssembler().assemble(reserve_formulation(), case)

    outcome = ReserveSolvePolicy().solve(built)

    audit = outcome.sos_support_polishing
    assert audit is not None
    assert audit.policy == "objective-improving-adjacent-sos-support-v1"
    assert audit.discovery_objective >= audit.baseline_objective - 1e-8
    assert audit.polished_objective >= audit.baseline_objective - 1e-8
    assert audit.objective_improvement >= -1e-8


def test_support_oracle_retries_lp_failure_at_native_support_tolerance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configurations = []
    accepted = object()

    class StubScipBackend:
        def solve_mip(self, model, configuration, *, warm_start_discrete=False):
            configurations.append(configuration)
            if len(configurations) == 1:
                raise SolverExecutionError("synthetic LP solver failure")
            return accepted

    monkeypatch.setattr(
        hvdc_formulation_module, "NativeScipBackend", StubScipBackend
    )

    result = ReserveSolvePolicy._solve_support_mip(
        SimpleNamespace(model=object())  # type: ignore[arg-type]
    )

    assert result is accepted
    assert [item.options["numerics/feastol"] for item in configurations] == [
        1e-9,
        1e-7,
    ]
    assert {item.options["time_limit_seconds"] for item in configurations} == {
        300.0
    }
