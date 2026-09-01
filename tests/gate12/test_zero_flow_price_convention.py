"""Probity tests for the independent zero-flow price-convention certificate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from tools.gate12.evidence import EvidenceContractError
from tools.gate12.zero_flow_price_convention import (
    PublicationContribution,
    ZeroFlowCaseInputs,
    ZeroFlowPriceConventionResult,
    ZeroFlowPriceConventionResultStore,
    ZeroFlowPriceConventionValidator,
)
from tools.gate12.zero_flow_price_runner import ZeroFlowPriceConventionRunner


def _inputs(
    *,
    flow: float | None = 0.0,
    leaf_generation: float = 0.0,
    leaf_load: float = 0.0,
    offer_nodes: frozenset[str] = frozenset(),
) -> ZeroFlowCaseInputs:
    branch_flow = None if flow is None else {"LINE": flow}
    return ZeroFlowCaseInputs(
        case_id="case",
        date_time="time",
        branches={"LINE": ("PARENT", "LEAF")},
        first_loss_factors={
            ("LINE", "forward"): 0.001,
            ("LINE", "backward"): 0.001,
        },
        electrical_buses=frozenset({"PARENT", "LEAF"}),
        bus_generation={"PARENT": 50.0, "LEAF": leaf_generation},
        bus_load={"PARENT": 50.0, "LEAF": leaf_load},
        branch_flow=branch_flow,
        node_buses={"NODE": frozenset({"LEAF"})},
        node_bus_allocation={("NODE", "LEAF"): 1.0},
        offer_nodes=offer_nodes,
        bid_nodes=frozenset(),
    )


def _prices() -> tuple[dict[str, float], dict[str, float]]:
    parent = 10.0
    return (
        {"PARENT": parent, "LEAF": parent * 0.999},
        {"PARENT": parent, "LEAF": parent / 0.999},
    )


def test_certifies_gams_export_side_against_documented_load_derivative() -> None:
    reference, candidate = _prices()
    certificate = ZeroFlowPriceConventionValidator().compare_case(
        inputs=_inputs(),
        reference_bus=reference,
        candidate_bus=candidate,
        reference_node={"NODE": reference["LEAF"]},
        candidate_node={"NODE": candidate["LEAF"]},
    )

    assert certificate.passed
    assert certificate.certified_bus_identities == ("LEAF",)
    assert certificate.certified_node_identities == ("NODE",)
    assert certificate.observations[0].reference_side == "export"
    assert certificate.observations[0].zero_flow_evidence == "reported-branch-flow"


def test_zero_injection_leaf_balance_is_an_explicit_zero_flow_proof() -> None:
    reference, candidate = _prices()
    certificate = ZeroFlowPriceConventionValidator().compare_case(
        inputs=_inputs(flow=None),
        reference_bus=reference,
        candidate_bus=candidate,
        reference_node={"NODE": reference["LEAF"]},
        candidate_node={"NODE": candidate["LEAF"]},
    )

    assert certificate.passed
    assert (
        certificate.observations[0].zero_flow_evidence == "zero-injection-leaf-balance"
    )


@pytest.mark.parametrize(
    ("inputs", "reason"),
    [
        (_inputs(flow=1.0), "nonzero-branch-flow"),
        (_inputs(leaf_generation=1.0), "nonzero-leaf-injection"),
        (_inputs(leaf_load=1.0), "nonzero-leaf-injection"),
        (_inputs(offer_nodes=frozenset({"NODE"})), "active-offer-or-bid-node"),
    ],
)
def test_rejects_a_leaf_without_zero_flow_passivity(
    inputs: ZeroFlowCaseInputs, reason: str
) -> None:
    reference, candidate = _prices()
    certificate = ZeroFlowPriceConventionValidator().compare_case(
        inputs=inputs,
        reference_bus=reference,
        candidate_bus=candidate,
        reference_node={"NODE": reference["LEAF"]},
        candidate_node={"NODE": candidate["LEAF"]},
    )

    assert not certificate.passed
    assert certificate.unresolved_bus_reasons == {"LEAF": reason}


def test_rejects_wrong_candidate_derivative_and_non_kink_reference() -> None:
    reference, candidate = _prices()
    wrong_candidate = {**candidate, "LEAF": 10.1}
    candidate_failure = ZeroFlowPriceConventionValidator().compare_case(
        inputs=_inputs(),
        reference_bus=reference,
        candidate_bus=wrong_candidate,
        reference_node={"NODE": reference["LEAF"]},
        candidate_node={"NODE": wrong_candidate["LEAF"]},
    )
    wrong_reference = {**reference, "LEAF": 9.8}
    reference_failure = ZeroFlowPriceConventionValidator().compare_case(
        inputs=_inputs(),
        reference_bus=wrong_reference,
        candidate_bus=candidate,
        reference_node={"NODE": wrong_reference["LEAF"]},
        candidate_node={"NODE": candidate["LEAF"]},
    )

    assert candidate_failure.unresolved_bus_reasons == {
        "LEAF": "candidate-not-load-derivative"
    }
    assert reference_failure.unresolved_bus_reasons == {
        "LEAF": "reference-not-kink-derivative"
    }


def test_rejects_node_delta_that_does_not_project_from_certified_buses() -> None:
    reference, candidate = _prices()
    certificate = ZeroFlowPriceConventionValidator().compare_case(
        inputs=_inputs(),
        reference_bus=reference,
        candidate_bus=candidate,
        reference_node={"NODE": reference["LEAF"]},
        candidate_node={"NODE": candidate["LEAF"] + 0.01},
    )

    assert not certificate.passed
    assert certificate.unresolved_node_reasons == {
        "NODE": "node-allocation-projection-mismatch"
    }


def test_publication_certificate_reconstructs_weighted_rounded_candidate() -> None:
    validator = ZeroFlowPriceConventionValidator()
    certificate = validator.compare_publication(
        trading_period="TP1",
        node="NODE",
        reference=10.0,
        candidate=10.66667,
        contributions=(
            PublicationContribution("case-1", "time-1", 100.0, 10.0),
            PublicationContribution("case-2", "time-2", 200.0, 11.0),
        ),
        decimals=5,
    )

    assert certificate.passed
    assert certificate.reconstructed_candidate == 10.66667
    assert certificate.total_seconds == 300.0


def test_publication_certificate_accepts_background_price_noise() -> None:
    certificate = ZeroFlowPriceConventionValidator().compare_publication(
        trading_period="TP1",
        node="NODE",
        reference=10.0,
        candidate=10.66665,
        contributions=(
            PublicationContribution("case-1", "time-1", 100.0, 10.0),
            PublicationContribution("case-2", "time-2", 200.0, 11.0),
        ),
        decimals=5,
    )

    assert certificate.reconstructed_candidate == 10.66667
    assert certificate.absolute_residual == pytest.approx(0.00002)
    assert certificate.passed


def test_publication_projection_ignores_disconnected_allocated_bus() -> None:
    class Evidence:
        @staticmethod
        def case_inputs(
            _case_id: str, _date_time: str, *, branch_flow: object
        ) -> ZeroFlowCaseInputs:
            assert branch_flow is None
            base = _inputs()
            return ZeroFlowCaseInputs(
                case_id=base.case_id,
                date_time=base.date_time,
                branches=base.branches,
                first_loss_factors=base.first_loss_factors,
                electrical_buses=base.electrical_buses,
                bus_generation=base.bus_generation,
                bus_load=base.bus_load,
                branch_flow=base.branch_flow,
                node_buses={"NODE": frozenset({"LEAF", "DEAD"})},
                node_bus_allocation={
                    ("NODE", "LEAF"): 1.0,
                    ("NODE", "DEAD"): 0.0,
                },
                offer_nodes=base.offer_nodes,
                bid_nodes=base.bid_nodes,
            )

        @staticmethod
        def case_bus_prices(_case_id: str, _date_time: str) -> dict[str, float]:
            reference, _candidate = _prices()
            return reference

    runner = object.__new__(ZeroFlowPriceConventionRunner)
    runner.validator = ZeroFlowPriceConventionValidator()

    assert runner._canonical_node_price(
        evidence=cast(Any, Evidence()),
        case_id="case",
        date_time="time",
        node="NODE",
    ) == pytest.approx(10.0 / 0.999)


def test_publication_projection_returns_zero_for_dead_node() -> None:
    class Evidence:
        @staticmethod
        def case_inputs(
            _case_id: str, _date_time: str, *, branch_flow: object
        ) -> ZeroFlowCaseInputs:
            assert branch_flow is None
            base = _inputs()
            return ZeroFlowCaseInputs(
                case_id=base.case_id,
                date_time=base.date_time,
                branches=base.branches,
                first_loss_factors=base.first_loss_factors,
                electrical_buses=base.electrical_buses,
                bus_generation=base.bus_generation,
                bus_load=base.bus_load,
                branch_flow=base.branch_flow,
                node_buses={"DEAD-NODE": frozenset({"DEAD"})},
                node_bus_allocation={("DEAD-NODE", "DEAD"): 1.0},
                offer_nodes=base.offer_nodes,
                bid_nodes=base.bid_nodes,
            )

        @staticmethod
        def case_bus_prices(_case_id: str, _date_time: str) -> dict[str, float]:
            reference, _candidate = _prices()
            return reference

    runner = object.__new__(ZeroFlowPriceConventionRunner)
    runner.validator = ZeroFlowPriceConventionValidator()

    assert runner._canonical_node_price(
        evidence=cast(Any, Evidence()),
        case_id="case",
        date_time="time",
        node="DEAD-NODE",
    ) == 0.0


def test_publication_certificate_rejects_wrong_candidate_or_missing_weight() -> None:
    validator = ZeroFlowPriceConventionValidator()
    wrong = validator.compare_publication(
        trading_period="TP1",
        node="NODE",
        reference=10.0,
        candidate=10.7,
        contributions=(PublicationContribution("case", "time", 300.0, 11.0),),
        decimals=5,
    )

    assert not wrong.passed
    with pytest.raises(ValueError, match="positive publication weight"):
        validator.compare_publication(
            trading_period="TP1",
            node="NODE",
            reference=10.0,
            candidate=10.0,
            contributions=(PublicationContribution("case", "time", 0.0, 10.0),),
            decimals=5,
        )


def test_daily_certificate_is_hash_bound_and_immutable(tmp_path: Path) -> None:
    reference, candidate = _prices()
    validator = ZeroFlowPriceConventionValidator()
    case = validator.compare_case(
        inputs=_inputs(),
        reference_bus=reference,
        candidate_bus=candidate,
        reference_node={"NODE": reference["LEAF"]},
        candidate_node={"NODE": candidate["LEAF"]},
    )
    publication = validator.compare_publication(
        trading_period="TP1",
        node="NODE",
        reference=9.99,
        candidate=10.01001,
        contributions=(PublicationContribution("case", "time", 300.0, 10.01001),),
        decimals=5,
    )
    result = ZeroFlowPriceConventionResult.create(
        trading_date="20221106",
        source_sha256="1" * 64,
        reference_result_gdx_sha256="2" * 64,
        reference_bundle_sha256="3" * 64,
        candidate_bundle_sha256="4" * 64,
        topology_sha256="5" * 64,
        cases=(case,),
        publications=(publication,),
    )
    target = tmp_path / "certificate.json"
    store = ZeroFlowPriceConventionResultStore()
    store.write(result, target)

    assert store.load(target).logical_sha256 == result.logical_sha256
    with pytest.raises(EvidenceContractError, match="already exists"):
        store.write(result, target)
    payload = json.loads(target.read_text())
    payload["topology_sha256"] = "6" * 64
    target.write_text(json.dumps(payload))
    with pytest.raises(EvidenceContractError, match="invalid result"):
        store.load(target)
