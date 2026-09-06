from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from pyspd import application
from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.orchestration import DailyRunner
from pyspd.reporting import ReportBundle
from tests.orchestration.conftest import (
    SequenceExecutor,
    make_daily_case,
    make_observation,
    make_prepared,
)


def test_report_uses_bundled_lock_outside_a_checkout(tmp_path, monkeypatch) -> None:
    package = tmp_path / "environment/lib/python3.13/site-packages/pyspd"
    package.mkdir(parents=True)
    module_path = package / "application.py"
    module_path.write_text("")
    bundled = package / "_build/uv.lock"
    bundled.parent.mkdir()
    bundled.write_bytes(b"version = 1\n# wheel build lock\n")
    monkeypatch.setattr(application, "__file__", str(module_path))
    monkeypatch.chdir(tmp_path)
    # An unrelated caller's lock must not be mistaken for this package's lock.
    (tmp_path / "uv.lock").write_bytes(b"unrelated project")
    source = tmp_path / "synthetic-input"
    source.write_bytes(b"fixture")
    configuration = ApplicationConfiguration(
        formulation_id="vspd-v5.0.6-reserve",
        input_path=source,
        output_directory=tmp_path / "reports",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        gams_system_directory=tmp_path,
    )
    app = PyspdApplication()
    daily = app.daily_configuration(configuration)
    case = replace(make_daily_case(), source_sha256=configuration.source_sha256)
    result = DailyRunner(SequenceExecutor([make_observation(case)])).run(
        daily, (make_prepared(case),)
    )
    bundle = app.render_report_bundle(configuration, result)
    assert (
        bundle.provenance.dependency_lock_sha256
        == hashlib.sha256(bundled.read_bytes()).hexdigest()
    )
    manifest = bundle.write(configuration.output_directory)
    restored = ReportBundle.read(configuration.output_directory)
    assert restored == bundle
    assert len(manifest.files) == 12


def test_release_dependencies_are_installable_without_uv_groups() -> None:
    import tomllib

    project = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    )["project"]
    assert any(dep.startswith("highspy") for dep in project["dependencies"])
    assert any(
        dep.startswith("gamspy") for dep in project["optional-dependencies"]["gdx"]
    )
    assert set(project["optional-dependencies"]) >= {"gdx", "clp", "cbc"}
