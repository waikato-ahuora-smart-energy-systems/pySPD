from __future__ import annotations

import pytest

from pyspd.contracts import CaseData
from pyspd.preprocess import Vspd506Preprocessor


def test_preprocessing_pipeline_is_deterministic_and_immutable(
    representative_case: CaseData,
) -> None:
    preprocessor = Vspd506Preprocessor()
    first = preprocessor.transform(representative_case)
    second = preprocessor.transform(representative_case)

    assert first.build_order == (
        "compatibility",
        "topology",
        "loss_curves",
        "offers_bids_load",
        "constraints_risk_scarcity",
    )
    assert first.structural_signature == second.structural_signature
    assert [item.logical_sha256 for item in first.checkpoints] == [
        item.logical_sha256 for item in second.checkpoints
    ]
    assert len(first.artifacts) == 100
    with pytest.raises(TypeError):
        first.artifacts["new"] = first.artifacts["node"]  # type: ignore[index]
    with pytest.raises(TypeError):
        first.parameter("required_load").values[("C1", "D1", "N1")] = 0.0  # type: ignore[index]


def test_wrong_formulation_is_rejected(representative_case: CaseData) -> None:
    incompatible = CaseData(
        "future-formulation",
        representative_case.identifier,
        representative_case.symbols,
    )
    with pytest.raises(ValueError, match="unsupported preprocessing formulation"):
        Vspd506Preprocessor().transform(incompatible)
