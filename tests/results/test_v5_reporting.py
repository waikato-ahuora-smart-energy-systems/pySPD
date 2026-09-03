from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest

from pyspd import reporting
from pyspd.orchestration import DailyRunConfiguration, DailyRunner
from pyspd.reporting import (
    ArtifactProvenance,
    ReportBundle,
    daily_report_registry,
)
from tests.orchestration.conftest import (
    SequenceExecutor,
    make_observation,
    make_prepared,
)

FORMULATION = "vspd-v5.0.6-reserve"


def _bundle(observation=None) -> ReportBundle:
    configuration = DailyRunConfiguration(FORMULATION, "0" * 64, 3)
    result = DailyRunner(SequenceExecutor([observation or make_observation()])).run(
        configuration, (make_prepared(),)
    )
    provenance = ArtifactProvenance(
        formulation_id=FORMULATION,
        source_sha256="0" * 64,
        configuration_sha256=configuration.logical_sha256,
        code_version="0.1.0",
        dependency_lock_sha256="1" * 64,
        solver_profile="scip-mip-fixed-highs-rmip",
        environment_fingerprint="test-arm64",
    )
    profile = daily_report_registry().resolve(FORMULATION)
    collected = profile.result_schema().collect(result, provenance)
    return profile.report_renderer().render(collected)


def test_v5_profile_selects_complete_typed_report_surface() -> None:
    bundle = _bundle()
    assert set(bundle.tables) == {
        "summary",
        "island",
        "bus",
        "node",
        "offer",
        "bid",
        "reserve",
        "risk",
        "branch",
        "constraint",
        "published_price",
        "audit",
    }
    assert bundle.provenance.formulation_id == FORMULATION
    assert bundle.tables["node"].rows
    assert bundle.tables["audit"].rows
    assert all(
        table.definition.formulation_id == FORMULATION
        for table in bundle.tables.values()
    )


def test_report_directory_round_trip_is_byte_deterministic(tmp_path) -> None:
    bundle = _bundle()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = bundle.write(first)
    restored = ReportBundle.read(first)
    second_manifest = restored.write(second)

    assert restored == bundle
    assert first_manifest.logical_sha256 == second_manifest.logical_sha256
    for name in first_manifest.files:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert (
            hashlib.sha256((first / name).read_bytes()).hexdigest()
            == first_manifest.files[name]
        )


def test_formulation_registry_rejects_unknown_or_duplicate_profiles() -> None:
    registry = daily_report_registry()
    profile = registry.resolve(FORMULATION)
    try:
        registry.register(profile)
    except ValueError as error:
        assert "duplicate" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("duplicate report profile was accepted")
    try:
        registry.resolve("vspd-v16")
    except ValueError as error:
        assert "unknown" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unknown report profile was accepted")


def test_model_rows_use_fixed_pricing_state_and_complete_branch_domain() -> None:
    model = pyo.ConcreteModel()
    model.ac_flow = pyo.Var([("case", "time", "AC.1")], initialize=12.5)
    model.hvdc_flow = pyo.Var([("case", "time", "HVDC.1")], initialize=25.0)
    primary = SimpleNamespace(
        model=model,
        case_data=SimpleNamespace(study_mode={("case", "time"): 101.0}),
        artifacts=SimpleNamespace(
            values={
                "branch_flow": model.ac_flow,
                "hvdc_flow": model.hvdc_flow,
                "network_data": SimpleNamespace(
                    report_branches={
                        ("case", "time", "AC.1"),
                        ("case", "time", "HVDC.1"),
                        ("case", "time", "OPEN.1"),
                    }
                ),
            }
        ),
    )
    raw_model = pyo.ConcreteModel()
    raw_model.ac_flow = pyo.Var([("case", "time", "AC.1")], initialize=999.0)
    raw_primary = SimpleNamespace(
        model=raw_model,
        artifacts=SimpleNamespace(values={"branch_flow": raw_model.ac_flow}),
    )
    rows: dict[str, list[dict[str, str]]] = {
        "bid": [],
        "risk": [],
        "branch": [],
        "constraint": [],
    }

    reporting._model_rows(
        rows,
        SimpleNamespace(primary_model=raw_primary, pricing_model=primary),
        {"case_id": "case", "date_time": "time"},
    )

    assert rows["branch"] == [
        {
            "case_id": "case",
            "date_time": "time",
            "branch": "AC.1",
            "flow_mw": "12.5",
        },
        {
            "case_id": "case",
            "date_time": "time",
            "branch": "HVDC.1",
            "flow_mw": "25",
        },
        {
            "case_id": "case",
            "date_time": "time",
            "branch": "OPEN.1",
            "flow_mw": "0",
        },
    ]

    rows["branch"].clear()
    primary.case_data.study_mode[("case", "time")] = 111.0
    reporting._model_rows(
        rows,
        SimpleNamespace(primary_model=raw_primary, pricing_model=primary),
        {"case_id": "case", "date_time": "time"},
    )
    assert {row["branch"] for row in rows["branch"]} == {"AC.1", "HVDC.1"}


def test_bus_report_uses_allocated_transferred_price_for_dead_node_bus() -> None:
    observation = make_observation()
    bus_keys = sorted(observation.raw_bus_prices)
    observation = replace(
        observation,
        bus_load={bus_keys[0]: 0.0, bus_keys[1]: 20.0},
        bus_electrical_island={bus_keys[0]: 0.0, bus_keys[1]: 1.0},
    )

    rows = {row["bus"]: row for row in _bundle(observation).tables["bus"].rows}

    assert rows[bus_keys[0][-1]]["raw_price_nzd_per_mwh"] == "50"
    assert rows[bus_keys[0][-1]]["repaired_price_nzd_per_mwh"] == "60"


def test_price_interval_is_reported_only_where_analytic_interval_exists() -> None:
    observation = make_observation()
    first_bus = min(observation.raw_bus_prices)
    observation = replace(
        observation,
        raw_bus_price_intervals={first_bus: (49.5, 50.5)},
    )

    bundle = _bundle(observation)
    buses = {row["bus"]: row for row in bundle.tables["bus"].rows}
    nodes = {row["node"]: row for row in bundle.tables["node"].rows}
    published = {
        row["location"]: row
        for row in bundle.tables["published_price"].rows
        if row["product"] == "energy"
    }

    assert buses["B1"]["price_interval"] == "[49.5,50.5]"
    assert buses["B2"]["price_interval"] == ""
    assert nodes["N1"]["price_interval"] == "[49.5,50.5]"
    assert nodes["N2"]["price_interval"] == ""
    assert published["N1"]["price_interval"] == "[49.5,50.5]"
    assert published["N2"]["price_interval"] == ""


def test_report_direction_treats_solver_noise_as_zero_forward_flow() -> None:
    assert reporting._branch_report_direction(-2.99e-11) == "forward"
    assert reporting._branch_report_direction(-1.0e-6) == "backward"


def test_island_load_counts_allocated_fixed_load_and_cleared_bid_once() -> None:
    network = SimpleNamespace(
        node_bus={
            ("C1", "T1", "N1", "B1"),
            ("C1", "T1", "N1", "B2"),
        },
        node_bus_allocation={
            ("C1", "T1", "N1", "B1"): 0.4,
            ("C1", "T1", "N1", "B2"): 0.6,
        },
        node_load={("C1", "T1", "N1"): 100.0},
    )

    assert reporting._island_report_load(
        network, ("C1", "T1"), {"B1", "B2"}, 12.5
    ) == pytest.approx(112.5)


def test_v5_renderer_projects_complete_authority_risk_and_summary_rows() -> None:
    ca, dt, island, reserve_class = "C1", "01-JAN-2024 00:00", "NI", "FIR"
    offer, risk_class = "OFFER", "genRisk"
    period = (ca, dt)
    risk_key = (*period, island, offer, reserve_class, risk_class)
    island_risk_key = (*period, island, reserve_class, risk_class)
    model = pyo.ConcreteModel()
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT_EXPORT)
    model.risk_definition = pyo.Constraint(expr=pyo.Constraint.Feasible)
    model.dual[model.risk_definition] = -0.125

    def variable(name, indices, values):
        component = pyo.Var(indices, initialize=values)
        model.add_component(name, component)
        return component

    artifacts = {
        "generation": variable("generation", [(*period, offer)], 137.0),
        "reserve": variable(
            "reserve",
            [(*period, offer, reserve_class, "PLRO")],
            1.25,
        ),
        "reserve_share_effective": variable("effective", [island_risk_key], 2.0),
        "reserve_shortfall_unit": variable("shortfall", [risk_key], 0.0),
        "reserve_deficit_ce": variable(
            "deficit_ce", [(*period, island, reserve_class)], 0.0
        ),
        "reserve_deficit_ece": variable(
            "deficit_ece", [(*period, island, reserve_class)], 0.0
        ),
        "balance_deficit": variable("balance_deficit", [(*period, "B1")], 0.1),
        "balance_surplus": variable("balance_surplus", [(*period, "B1")], 0.2),
        "branch_flow_surplus": variable("branch_flow_surplus", [(*period, "BR1")], 0.3),
        "ramp_deficit": variable("ramp_deficit", [(*period, offer)], 0.4),
        "ramp_surplus": variable("ramp_surplus", [(*period, offer)], 0.5),
        "branch_constraint_deficit": variable(
            "branch_constraint_deficit", [(*period, "BC1")], 0.6
        ),
        "branch_constraint_surplus": variable(
            "branch_constraint_surplus", [(*period, "BC1")], 0.7
        ),
        "market_node_constraint_deficit": variable(
            "market_node_constraint_deficit", [(*period, "MC1")], 0.8
        ),
        "market_node_constraint_surplus": variable(
            "market_node_constraint_surplus", [(*period, "MC1")], 0.9
        ),
    }
    model.system_cost = pyo.Var([period], initialize=20.0)
    model.system_benefit = pyo.Var([period], initialize=1.0)
    model.system_penalty = pyo.Var([period], initialize=0.5)
    artifacts.update(
        {
            "system_cost_by_period": model.system_cost,
            "system_benefit_by_period": model.system_benefit,
            "system_penalty_by_period": model.system_penalty,
            "risk_definition_constraints": {("GEN", *risk_key): model.risk_definition},
        }
    )
    reserve_data = SimpleNamespace(
        ce_risks={risk_class},
        offer_island={(*period, offer, island)},
        primary_secondary_offer=set(),
        risk_group_offer=set(),
        fk_band={(*period, offer): 0.5},
        free_reserve={island_risk_key: 2.0},
        risk_minimum={},
        modulation_risk_class={},
    )
    case_data = SimpleNamespace(
        reserve=reserve_data,
        study_mode={period: 101.0},
        scarcity_blocks={(*period, "N1", "BLK1")},
        scarcity_limit={(*period, "N1", "BLK1"): 100.0},
        scarcity_price={(*period, "N1", "BLK1"): 10.0},
    )
    pricing = SimpleNamespace(
        model=model,
        artifacts=SimpleNamespace(values=artifacts),
        case_data=case_data,
    )
    observation = replace(
        make_observation(),
        reserve_prices={(*period, island, reserve_class): 0.0085},
        objective=-19.5,
        solve_payload=SimpleNamespace(pricing_model=pricing),
    )

    bundle = _bundle(observation)
    risk = bundle.tables["risk"].rows
    summary = bundle.tables["summary"].rows[0]

    assert risk == (
        {
            "case_id": ca,
            "date_time": dt,
            "island": island,
            "reserve_class": reserve_class,
            "risk_class": "CE",
            "risk_type": "GEN",
            "risk_setter": offer,
            "covered_energy_mw": "137",
            "covered_reserve_mw": "1.25",
            "covered_fk_band_mw": "0.5",
            "risk_subtractor_mw": "2",
            "reserve_mw": "3.25",
            "shortfall_mw": "0",
            "deficit_mw": "0",
            "reserve_price_nzd_per_mwh": "0.0085000000000000006",
            "risk_price_nzd_per_mwh": "0.125",
        },
    )
    assert summary["status_code"] == "1"
    assert summary["system_ofv_nzd"] == "980.5"
    assert summary["system_cost_nzd"] == "20"
    assert summary["system_benefit_nzd"] == "1"
    assert summary["violation_cost_nzd"] == "0.5"
    assert summary["deficit_generation_mw"] == "0.10000000000000001"
    assert summary["surplus_market_node_constraint_mw"] == "0.90000000000000002"

    case_data.study_mode[period] = 111.0
    legacy_summary = _bundle(observation).tables["summary"].rows[0]
    assert legacy_summary["system_ofv_nzd"] == "-19.5"
