"""CPLEX-gold regression for the 2023-09-22 TP4 reserve-loss kink."""

from __future__ import annotations

import hashlib
import json
from importlib.util import find_spec
from pathlib import Path

import pyomo.environ as pyo
import pytest

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.reserve import (
    RESERVE_FORMULATION_ID,
    IndependentReserveValidator,
)
from tests.evidence_support import require_external_evidence

_ROOT = Path(__file__).parents[2]
_GAMS = Path("/Library/Frameworks/GAMS.framework/Resources")
_INPUT = (
    _ROOT
    / "tests/fixtures/cplex_reference/2023/20230922/input/Pricing_20230922.gdx"
)
_CASE_ID = "211012023091330496"
_DATETIME = "22-SEP-2023 01:30"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_tp4_reserve_kink_evidence_is_hash_bound() -> None:
    require_external_evidence(_INPUT, "cplex-reference-v1")
    evidence_path = _ROOT / "private/docs/gate-12/cplex-tp4-reserve-kink-20230922.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    logical_sha256 = evidence.pop("logical_sha256")

    assert logical_sha256 == hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert evidence["diagnosis"]["accepted"]
    assert evidence["diagnosis"]["objective_loss_nzd"] <= evidence["policy"][
        "objective_loss_budget_nzd"
    ]
    assert evidence["source"]["input_sha256"] == _sha256(_INPUT)
    for key, name in (
        (
            "benchmark_sha256",
            "cplex-reference-paths-20230922-tp4-reserve-kink.json",
        ),
        (
            "comparison_file_sha256",
            "cplex-reference-comparison-20230922-tp4-reserve-kink.json",
        ),
    ):
        assert evidence["evidence"][key] == _sha256(_ROOT / "private/docs/gate-12" / name)
    benchmark = json.loads(
        (
            _ROOT
            / "private/docs/gate-12/cplex-reference-paths-20230922-tp4-reserve-kink.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        evidence["evidence"]["records_sha256"]
        == benchmark["runs"][0]["records_sha256"]
    )


def test_tp4_prefix_publishes_the_cplex_si_fir_price() -> None:
    benchmark_path = (
        _ROOT / "private/docs/gate-12/cplex-reference-paths-20230922-tp4-reserve-kink.json"
    )
    require_external_evidence(benchmark_path, "gate12-solver-paths-v1")
    benchmark = json.loads(
        benchmark_path.read_text(encoding="utf-8")
    )
    run = benchmark["runs"][0]
    rows = [
        row
        for row in run["published_price_rows"]
        if row["trading_period"] == "TP4"
        and row["product"] == "FIR"
        and row["location"] == "SI"
    ]

    assert run["completed"]
    assert run["all_solves_optimal"]
    assert run["case_count"] == 25
    assert len(rows) == 1
    assert float(rows[0]["price_nzd_per_mwh"]) == pytest.approx(0.07585)


@pytest.mark.oracle
@pytest.mark.skipif(
    find_spec("gamspy") is None or not _GAMS.is_dir(),
    reason="requires the optional GDX reader and an installed GAMS runtime",
)
def test_tp4_reserve_breakpoint_reproduces_cplex_prices_and_quantities(
    tmp_path: Path,
) -> None:
    require_external_evidence(_INPUT, "cplex-reference-v1")
    configuration = ApplicationConfiguration(
        formulation_id=RESERVE_FORMULATION_ID,
        input_path=_INPUT,
        output_directory=tmp_path,
        source_sha256=hashlib.sha256(_INPUT.read_bytes()).hexdigest(),
        gams_system_directory=_GAMS,
        case_ids=(_CASE_ID,),
    )
    application = PyspdApplication()
    prepared = next(application.iter_prepared_cases(configuration))
    observation = application.case_executor(configuration).solve(prepared)
    outcome = observation.solve_payload
    audit = outcome.pricing_canonicalization

    assert audit is not None
    assert audit.policy == "reserve-boundary-and-zero-price-surplus-v3"
    assert audit.accepted_targets == {
        f"{_CASE_ID}|{_DATETIME}|SI|FIR|backward": pytest.approx(0.0)
    }
    assert audit.objective_loss == pytest.approx(0.0007119591, abs=1e-8)
    assert audit.objective_loss <= audit.allowed_objective_loss
    # The existing native-SCIP SOS reconstruction boundary is 2e-4 MW on this
    # case; the three canonicalization-specific residuals remain near machine
    # precision and are asserted independently below.
    validation = IndependentReserveValidator().validate(outcome, tolerance=2e-4)
    assert validation.passed, max(
        validation.residuals.items(), key=lambda item: item[1]
    )
    assert max(
        value
        for name, value in validation.residuals.items()
        if name.startswith("pricing_canonicalization_")
    ) <= 1e-9
    assert observation.reserve_prices == pytest.approx(
        {
            (_CASE_ID, _DATETIME, "NI", "FIR"): 0.09,
            (_CASE_ID, _DATETIME, "NI", "SIR"): 0.100769069772,
            (_CASE_ID, _DATETIME, "SI", "FIR"): 0.1,
            (_CASE_ID, _DATETIME, "SI", "SIR"): 0.1,
        }
    )

    model = outcome.pricing_model.model
    sent = model.ReserveSharing.HVDCSent[_CASE_ID, _DATETIME, "SI"]
    received = model.ReserveSharing.ReserveShareReceived[
        _CASE_ID, _DATETIME, "SI", "FIR", "backward"
    ]
    ni_sent = model.ReserveSharing.ReserveShareSent[
        _CASE_ID, _DATETIME, "NI", "FIR", "backward"
    ]
    si_sent = model.ReserveSharing.ReserveShareSent[
        _CASE_ID, _DATETIME, "SI", "FIR", "forward"
    ]

    assert pyo.value(sent) == pytest.approx(69.23097, abs=5e-6)
    assert pyo.value(received) == pytest.approx(69.23097, abs=5e-6)
    assert pyo.value(ni_sent) == pytest.approx(68.68194, abs=5e-6)
    assert pyo.value(si_sent) == pytest.approx(38.74799, abs=5e-6)
    assert pyo.value(outcome.pricing_model.artifacts["system_cost"]) == pytest.approx(
        11826.67400, abs=5e-6
    )

    case = prepared.payload
    assert case.network is not None
    reference_prices = {
        case.node_region[node][2]: sum(
            weight * observation.raw_bus_prices[node[0], node[1], bus]
            for ca, dt, source_node, bus in case.network.node_bus
            if (ca, dt, source_node) == node
            for weight in (case.network.node_bus_allocation[ca, dt, source_node, bus],)
        )
        for node in case.network.reference_nodes
    }
    assert reference_prices == pytest.approx(
        {"NI": 84.37596, "SI": 83.77470}, abs=5e-6
    )
