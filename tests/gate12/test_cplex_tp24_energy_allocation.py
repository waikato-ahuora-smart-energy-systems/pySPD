"""Source-backed probity tests for the TP24 equal-price allocation."""

from __future__ import annotations

import csv
import hashlib
import json
from importlib.util import find_spec
from pathlib import Path

import pytest

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.reserve import RESERVE_FORMULATION_ID
from tests.evidence_support import require_external_evidence
from tools.compare_cplex_reference import (
    _case_candidate,
    _case_reference,
    _load_reference,
)
from tools.gate12.energy_allocation import EnergyAllocationCertificateStore
from tools.gate12.evidence import EvidenceContractError
from tools.gate12.report_row_parity import ReportRowParityValidator

_ROOT = Path(__file__).parents[2]
_GAMS = Path("/Library/Frameworks/GAMS.framework/Resources")
_INPUT = (
    _ROOT
    / "tests/fixtures/cplex_reference/2023/20230922/input/Pricing_20230922.gdx"
)
_RESULTS = _ROOT / "tests/fixtures/cplex_reference/2023/20230922/results"
_BENCHMARK = (
    _ROOT
    / "private/docs/gate-12/cplex-reference-paths-20230922-tp24-passive-tree-six-cases.json"
)
_RECORDS = (
    _ROOT
    / "private/docs/gate-12/cplex-reference-paths-20230922-tp24-passive-tree-six-cases-scip-mip-fixed-highs-rmip.jsonl"
)
_CERTIFICATE = (
    _ROOT / "private/docs/gate-12/cplex-tp24-energy-allocation-20230922.json"
)
_FULL_BENCHMARK = (
    _ROOT
    / "private/docs/gate-12/cplex-reference-paths-20230922-highs-root-boundary-interval.json"
)
_FULL_RECORDS = (
    _ROOT
    / "private/docs/gate-12/cplex-reference-paths-20230922-highs-root-boundary-interval-scip-mip-fixed-highs-rmip.jsonl"
)
_FULL_CERTIFICATE = (
    _ROOT
    / "private/docs/gate-12/cplex-tp24-energy-allocation-20230922-full-day.json"
)
_FULL_COMPARISON = (
    _ROOT
    / "private/docs/gate-12/cplex-reference-comparison-20230922-highs-root-boundary-interval-tp24-allocation.json"
)
_UNCERTIFIED_FULL_COMPARISON = (
    _ROOT
    / "private/docs/gate-12/cplex-reference-comparison-20230922-highs-root-boundary-interval.json"
)
_CASE_ID = "211012023092330682"
_DATETIME = "22-SEP-2023 11:30"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record() -> dict[str, object]:
    return json.loads(_RECORDS.read_text(encoding="utf-8").splitlines()[0])


def test_tp24_certificate_is_bound_and_resolves_only_the_case_rows() -> None:
    require_external_evidence(_INPUT, "cplex-reference-v1")
    require_external_evidence(_BENCHMARK, "gate12-solver-paths-v1")
    require_external_evidence(_RECORDS, "gate12-solver-paths-v1")
    certificate = EnergyAllocationCertificateStore().load(_CERTIFICATE)
    benchmark = json.loads(_BENCHMARK.read_text(encoding="utf-8"))
    record = _record()

    assert certificate.source_sha256 == _sha256(_INPUT)
    assert certificate.benchmark_sha256 == _sha256(_BENCHMARK)
    assert certificate.records_sha256 == benchmark["runs"][0]["records_sha256"]
    assert certificate.records_sha256 == _sha256(_RECORDS)
    assert len(certificate.accepted_identities) == 14
    assert not certificate.certifies(
        (_CASE_ID, _DATETIME, "TUI1101 KTW0", "GENE", "generation-mw")
    )
    assert not certificate.certifies(
        (_CASE_ID, _DATETIME, "TUI_T6.T6", "308", "302", "branch-flow-mw")
    )

    reference = _load_reference(_RESULTS, year=2023)
    reference_payload = _case_reference(reference, record, year=2023)
    candidate_payload = _case_candidate(
        record, reference_payload, normalize_v4_island_load=False
    )
    validator = ReportRowParityValidator()
    strict = validator.compare(
        case_id=_CASE_ID,
        reference=json.dumps(reference_payload, sort_keys=True).encode(),
        candidate=json.dumps(candidate_payload, sort_keys=True).encode(),
    )
    certified = validator.compare(
        case_id=_CASE_ID,
        reference=json.dumps(reference_payload, sort_keys=True).encode(),
        candidate=json.dumps(candidate_payload, sort_keys=True).encode(),
        energy_allocation_certificate=certificate,
    )

    assert strict.above_precision_count == 12
    assert certified.passed
    assert certified.above_precision_count == 0
    assert certified.certified_difference_count == (
        strict.certified_difference_count + 12
    )


def test_tp24_certificate_fails_closed_when_tampered(tmp_path: Path) -> None:
    payload = json.loads(_CERTIFICATE.read_text(encoding="utf-8"))
    payload["accepted_identities"].append(
        [_CASE_ID, _DATETIME, "TUI1101 KTW0", "GENE", "generation-mw"]
    )
    tampered = tmp_path / "tampered-energy-allocation.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvidenceContractError, match="certificate hash mismatch"):
        EnergyAllocationCertificateStore().load(tampered)


def test_tp24_full_day_certificate_and_comparison_are_bound() -> None:
    require_external_evidence(_INPUT, "cplex-reference-v1")
    require_external_evidence(_FULL_BENCHMARK, "gate12-solver-paths-v1")
    require_external_evidence(_FULL_RECORDS, "gate12-solver-paths-v1")
    sample = EnergyAllocationCertificateStore().load(_CERTIFICATE)
    certificate = EnergyAllocationCertificateStore().load(_FULL_CERTIFICATE)
    benchmark = json.loads(_FULL_BENCHMARK.read_text(encoding="utf-8"))
    comparison = json.loads(_FULL_COMPARISON.read_text(encoding="utf-8"))
    uncertified = json.loads(
        _UNCERTIFIED_FULL_COMPARISON.read_text(encoding="utf-8")
    )
    profile = comparison["profiles"][0]
    uncertified_profile = uncertified["profiles"][0]

    assert certificate.source_sha256 == _sha256(_INPUT)
    assert certificate.benchmark_sha256 == _sha256(_FULL_BENCHMARK)
    assert certificate.records_sha256 == _sha256(_FULL_RECORDS)
    assert certificate.records_sha256 == benchmark["runs"][0]["records_sha256"]
    assert certificate.accepted_identities == sample.accepted_identities
    assert profile["complete"]
    assert profile["case_count"] == 274
    assert profile["all_solves_optimal"]
    assert profile["compared_value_count"] == 3_964_736
    assert profile["certified_difference_count"] == (
        uncertified_profile["certified_difference_count"] + 14
    )
    assert profile["above_precision_count"] == (
        uncertified_profile["above_precision_count"] - 14
    )


@pytest.mark.oracle
@pytest.mark.skipif(
    find_spec("gamspy") is None or not _GAMS.is_dir(),
    reason="requires the optional GDX reader and an installed GAMS runtime",
)
def test_tp24_certificate_matches_source_blocks_and_lossless_star(
    tmp_path: Path,
) -> None:
    require_external_evidence(_INPUT, "cplex-reference-v1")
    require_external_evidence(_RECORDS, "gate12-solver-paths-v1")
    certificate = EnergyAllocationCertificateStore().load(_CERTIFICATE)
    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=_INPUT,
        output_directory=tmp_path,
        source_sha256=_sha256(_INPUT),
        gams_system_directory=_GAMS,
        case_ids=(_CASE_ID,),
    )
    prepared = next(PyspdApplication().iter_prepared_cases(configuration))
    case = prepared.payload
    network = case.network
    assert network is not None

    pri = (_CASE_ID, _DATETIME, "TUI1101 PRI0")
    tui = (_CASE_ID, _DATETIME, "TUI1101 TUI0")
    assert (case.offer_limit[*pri, "t1"], case.offer_price[*pri, "t1"]) == (
        13.8,
        0.001,
    )
    assert (case.offer_limit[*pri, "t2"], case.offer_price[*pri, "t2"]) == (
        8.2,
        certificate.marginal_block_price,
    )
    assert (case.offer_limit[*tui, "t1"], case.offer_price[*tui, "t1"]) == (
        18.5,
        0.001,
    )
    assert (case.offer_limit[*tui, "t2"], case.offer_price[*tui, "t2"]) == (
        16.5,
        certificate.marginal_block_price,
    )

    candidate = _record()["reports"]
    candidate_offer = {
        row["offer"]: float(row["generation_mw"])
        for row in candidate["offer"]
        if row["offer"] in {pri[2], tui[2]}
    }
    with (_RESULTS / "2023-09-22_base_offer_results.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        reference_offer = {
            row["Offer"]: float(row["Generation (MW)"])
            for row in csv.DictReader(handle)
            if row["CaseID"] == _CASE_ID and row["Offer"] in {pri[2], tui[2]}
        }
    differences = {
        offer: candidate_offer[offer] - reference_offer[offer]
        for offer in candidate_offer
    }
    assert differences == pytest.approx(
        {pri[2]: certificate.transferred_mw, tui[2]: -certificate.transferred_mw}
    )
    assert sum(reference_offer.values()) == pytest.approx(
        sum(candidate_offer.values())
    )
    assert reference_offer[pri[2]] == pytest.approx(case.offer_limit[*pri, "t1"])
    assert candidate_offer[pri[2]] < sum(
        case.offer_limit[key] for key in case.offer_blocks if key[:3] == pri
    )
    assert min(reference_offer[tui[2]], candidate_offer[tui[2]]) > case.offer_limit[
        *tui, "t1"
    ]

    expected_buses = {
        "TUI1101 PRI0": {"303": 0.5, "304": 0.5},
        "TUI1101 TUI0": {"305": 1 / 3, "306": 1 / 3, "307": 1 / 3},
    }
    leaf_buses: set[str] = set()
    for offer, buses in expected_buses.items():
        offer_key = (_CASE_ID, _DATETIME, offer)
        nodes = {
            key[3] for key in network.offer_node if key[:3] == offer_key
        }
        assert nodes == {offer}
        assert network.node_load[offer_key] == 0.0
        actual = {
            key[3]: network.node_bus_allocation[key]
            for key in network.node_bus
            if key[:3] == offer_key
        }
        assert actual == pytest.approx(buses)
        leaf_buses.update(buses)

    certified_branches = {
        identity[2]
        for identity in certificate.accepted_identities
        if identity[-1] == "branch-flow-mw"
    }
    assert certified_branches == {
        "TUI_T1.T1",
        "TUI_T2.T2",
        "TUI_T3.T3",
        "TUI_T4.T4",
        "TUI_T5.T5",
    }
    for name in certified_branches:
        branch = (_CASE_ID, _DATETIME, name)
        from_buses = {
            key[3] for key in network.branch_from_bus if key[:3] == branch
        }
        to_buses = {key[3] for key in network.branch_to_bus if key[:3] == branch}
        assert from_buses == {"308"}
        assert len(to_buses) == 1
        assert to_buses <= leaf_buses
        assert network.branch_fixed_loss[branch] == 0.0
        assert network.branch_capacity[*branch, "forward"] == 2000.0
        assert network.branch_capacity[*branch, "backward"] == 2000.0
        assert all(
            value == 0.0
            for key, value in network.ac_loss_segment_factor.items()
            if key[:3] == branch
        )
        assert not any(
            value != 0.0 and key[3] == name
            for key, value in network.branch_constraint_factor.items()
        )
