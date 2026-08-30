"""Probity tests for exact twelve-surface PySPD evidence export."""

from __future__ import annotations

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
