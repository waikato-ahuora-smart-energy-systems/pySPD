"""Probity tests for exact twelve-surface PySPD evidence export."""

from __future__ import annotations

import json

import pytest

from pyspd.application import ApplicationRun
from pyspd.orchestration import DailyRunConfiguration, DailyRunner
from pyspd.reporting import ArtifactProvenance, ReportBundle, daily_report_registry
from tests.orchestration.conftest import (
    SequenceExecutor,
    make_observation,
    make_prepared,
)
from tools.gate12.evidence import REQUIRED_E2E_SURFACES
from tools.gate12.pyspd_surfaces import (
    PARTIAL_E2E_SURFACES,
    PyspdCaseSurfaceExporter,
    _common_fixed_state,
)

FORMULATION = "vspd-v5.0.6-reserve"


def _run(tmp_path, *, raw_prices: tuple[float, float] = (50.0, 60.0)):
    configuration = DailyRunConfiguration(FORMULATION, "0" * 64, 3)
    result = DailyRunner(
        SequenceExecutor([make_observation(raw_prices=raw_prices)])
    ).run(configuration, (make_prepared(),))
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
    bundle = profile.report_renderer().render(
        profile.result_schema().collect(result, provenance)
    )
    output = tmp_path / f"run-{raw_prices[0]}"
    manifest = bundle.write(output)
    return ApplicationRun(result, manifest, output)


def test_exporter_emits_exact_deterministic_case_surfaces(tmp_path) -> None:
    run = _run(tmp_path)
    exporter = PyspdCaseSurfaceExporter()

    first = exporter.export(run, trading_date="20240101")
    second = exporter.export(run, trading_date="20240101")

    assert first == second
    assert len(first) == 1
    assert set(first[0].surfaces) == set(REQUIRED_E2E_SURFACES)
    assert all(payload.endswith(b"\n") for payload in first[0].surfaces.values())
    assert all(len(value) == 64 for value in first[0].surface_sha256.values())
    with pytest.raises(TypeError):
        first[0].surfaces["node-price"] = b"tampered"  # type: ignore[index]


def test_exporter_keeps_price_layers_independently_hashable(tmp_path) -> None:
    baseline = PyspdCaseSurfaceExporter().export(
        _run(tmp_path, raw_prices=(50.0, 60.0)), trading_date="20240101"
    )[0]
    changed = PyspdCaseSurfaceExporter().export(
        _run(tmp_path, raw_prices=(51.0, 60.0)), trading_date="20240101"
    )[0]

    assert (
        baseline.surface_sha256["case-selection"]
        == changed.surface_sha256["case-selection"]
    )
    assert (
        baseline.surface_sha256["raw-bus-price"]
        != changed.surface_sha256["raw-bus-price"]
    )
    assert (
        baseline.surface_sha256["report-field"]
        != changed.surface_sha256["report-field"]
    )


def test_partial_export_can_be_completed_after_model_release(tmp_path) -> None:
    run = _run(tmp_path)
    exporter = PyspdCaseSurfaceExporter()
    reports = ReportBundle.read(run.output_directory)

    partial = exporter.export_partial(
        run.result.cases[0], reports, trading_date="20240101"
    )
    assert run.result.published is not None
    completed = exporter.complete(partial, run.result.published)

    assert set(partial.surfaces) == PARTIAL_E2E_SURFACES
    assert completed == exporter.export(run, trading_date="20240101")[0]


def test_common_surface_removes_python_only_structure_and_events(tmp_path) -> None:
    surface = PyspdCaseSurfaceExporter().export(
        _run(tmp_path), trading_date="20240101"
    )[0]

    physics = json.loads(surface.surfaces["primary-physics"])
    transition = json.loads(surface.surfaces["state-transition"])
    fixed = json.loads(surface.surfaces["fixed-discrete-pricing-state"])
    assert physics["structural_signature"] is None
    assert physics["variables"] == []
    assert transition["events"] == []
    assert fixed["primary_structural_signature"] is None
    assert fixed["pricing_structural_signature"] is None


def test_common_fixed_state_maps_shared_semantics_and_drops_encoding_binaries() -> None:
    case_id = "C1"
    date_time = "01-JAN-2024 00:00"
    discrete, sos = _common_fixed_state(
        {
            f"ReserveSharing.HVDCSending['{case_id}','{date_time}',NI]": 1.0,
            f"ReserveSharing.HVDCSendZero['{case_id}','{date_time}',NI]": 0.0,
            f"ReserveSharing.InZone['{case_id}','{date_time}',NI,FIR,NR]": 1.0,
            f"ReserveSharing.LambdaHVDCEnergyInterval['{case_id}','{date_time}',NI,ls1]": 1.0,
        },
        {
            f"ReserveSharing.LambdaHVDCEnergy['{case_id}','{date_time}',NI,ls1]": 1.0,
            f"ReserveSharing.LambdaHVDCReserve['{case_id}','{date_time}',NI,FIR,forward,ls1]": 1.0,
        },
    )

    assert discrete == {
        ("hvdc-sending", case_id, date_time, "NI"): 1.0,
        ("in-zone", case_id, date_time, "NI", "FIR", "NR"): 1.0,
    }
    assert sos == {
        ("hvdc-energy-lambda", case_id, date_time, "NI", "ls1"): 1.0,
        (
            "hvdc-reserve-lambda",
            case_id,
            date_time,
            "NI",
            "FIR",
            "forward",
            "ls1",
        ): 1.0,
    }
