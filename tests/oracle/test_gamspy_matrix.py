"""Probity tests for fixed-LP equation marginal recovery."""

from __future__ import annotations

import pandas as pd
import pytest

from tools.oracle.gamspy_matrix import (
    _equation_marginals,
    _require_optimal,
    _variable_levels,
)


def test_equation_marginals_restore_original_names_and_filter() -> None:
    index = pd.DataFrame(
        {
            "uni": ["e1", "e2"],
            "element_text": ["ObjectiveFunction", "EnergyBalance(NI)"],
        }
    )
    solution = pd.DataFrame(
        {
            "i": ["e1", "e2"],
            "level": [0.0, 0.0],
            "marginal": [1.0, 123.45],
        }
    )

    assert _equation_marginals(
        index, solution, equation_contains=("EnergyBalance",)
    ) == {"EnergyBalance(NI)": 123.45}


def test_variable_levels_restore_names_and_omit_inactive_sos_members() -> None:
    index = pd.DataFrame(
        {
            "uni": ["x1", "x2"],
            "element_text": ["Direction(A)", "Direction(B)"],
        }
    )
    solution = pd.DataFrame(
        {"s": ["s1", "s1"], "j": ["x1", "x2"], "level": [0.0, 0.75]}
    )

    assert _variable_levels(index, solution, include_zero=False) == {
        "Direction(B)": 0.75
    }


def test_matrix_oracle_rejects_nonoptimal_stage() -> None:
    with pytest.raises(RuntimeError, match="primary MIP did not return"):
        _require_optimal("ModelStatus.InfeasibleGlobal", "primary MIP")
