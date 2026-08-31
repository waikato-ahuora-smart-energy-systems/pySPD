from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pyomo.environ as pyo

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


def _bundle() -> ReportBundle:
    configuration = DailyRunConfiguration(FORMULATION, "0" * 64, 3)
    result = DailyRunner(SequenceExecutor([make_observation()])).run(
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


def test_model_rows_include_ac_and_hvdc_branch_flows() -> None:
    model = pyo.ConcreteModel()
    model.ac_flow = pyo.Var([("case", "time", "AC.1")], initialize=12.5)
    model.hvdc_flow = pyo.Var([("case", "time", "HVDC.1")], initialize=25.0)
    primary = SimpleNamespace(
        model=model,
        artifacts=SimpleNamespace(
            values={
                "branch_flow": model.ac_flow,
                "hvdc_flow": model.hvdc_flow,
            }
        ),
    )
    rows: dict[str, list[dict[str, str]]] = {
        "bid": [],
        "risk": [],
        "branch": [],
        "constraint": [],
    }

    reporting._model_rows(
        rows,
        SimpleNamespace(primary_model=primary),
        {"case_id": "case", "date_time": "time"},
    )

    assert rows["branch"] == [
        {
            "case_id": "case",
            "date_time": "time",
            "branch": "case|time|AC.1",
            "flow_mw": "12.5",
        },
        {
            "case_id": "case",
            "date_time": "time",
            "branch": "case|time|HVDC.1",
            "flow_mw": "25",
        },
    ]
