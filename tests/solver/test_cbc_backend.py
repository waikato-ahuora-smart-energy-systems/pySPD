from __future__ import annotations

import pyomo.environ as pyo
import pytest

from pyspd.architecture import ModelAssembler
from pyspd.hvdc import hvdc_formulation
from pyspd.solver import CbcBackend, SolverConfiguration, SolveStatus
from tests.hvdc.conftest import make_hvdc_case


def test_cbc_preserves_native_sos2_and_loads_optimal_mip() -> None:
    built = ModelAssembler().assemble(
        hvdc_formulation(),
        make_hvdc_case(enforce=True, native_sos=True),
    )
    assert len(tuple(built.model.component_data_objects(pyo.SOSConstraint))) == 1

    result = CbcBackend().solve_mip(
        built.model,
        SolverConfiguration(
            {
                "time_limit_seconds": 60.0,
                "relative_gap": 0.0,
                "threads": 1,
            }
        ),
    )

    assert result.solve.status is SolveStatus.OPTIMAL
    assert result.solve.backend == "cbc"
    assert result.has_incumbent
    assert result.discrete_variable_count == 2
    objective = next(built.model.component_data_objects(pyo.Objective, active=True))
    assert pyo.value(objective) == pytest.approx(-416.66666667)
