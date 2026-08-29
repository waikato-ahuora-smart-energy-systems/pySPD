from dataclasses import replace

from pyspd.contracts import CaseData
from pyspd.preprocess import Vspd506Preprocessor, validate_preprocessing_invariants


def test_independent_invariants_pass_representative_case(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor().transform(representative_case)
    report = validate_preprocessing_invariants(result)

    assert report.passed
    assert {check.name for check in report.checks} == {
        "node-domain-closure",
        "bus-allocation-normalization",
        "active-branch-endpoint-closure",
        "loss-curve-monotonicity",
        "participant-block-consistency",
        "checkpoint-name-uniqueness",
    }
    assert len(report.logical_sha256) == 64


def test_invariant_checker_detects_allocation_mutation(
    representative_case: CaseData,
) -> None:
    result = Vspd506Preprocessor().transform(representative_case)
    artifacts = dict(result.artifacts)
    allocation = result.parameter("bus_node_allocation_factor")
    artifacts["bus_node_allocation_factor"] = replace(
        allocation,
        values={**allocation.values, ("C1", "D1", "B1", "N1"): 0.5},
    )
    mutated = replace(result, artifacts=artifacts)

    report = validate_preprocessing_invariants(mutated)
    assert not report.passed
    assert next(
        check for check in report.checks if check.name == "bus-allocation-normalization"
    ).violations
