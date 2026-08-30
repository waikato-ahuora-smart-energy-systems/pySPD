"""Probity tests for Gate 12 execution-source fingerprints."""

from __future__ import annotations

from tools.gate12.execution_provenance import (
    gams_execution_sha256,
    python_execution_sha256,
)


def test_python_execution_fingerprint_is_path_and_content_sensitive(tmp_path) -> None:
    (tmp_path / "src" / "pyspd").mkdir(parents=True)
    (tmp_path / "tools" / "gate12").mkdir(parents=True)
    (tmp_path / "tools" / "oracle").mkdir(parents=True)
    (tmp_path / "src" / "pyspd" / "model.py").write_text("value = 1\n")
    (tmp_path / "tools" / "gate12" / "runner.py").write_text("run = 1\n")
    (tmp_path / "tools" / "oracle" / "solver.py").write_text("solve = 1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")

    first = python_execution_sha256(tmp_path)
    (tmp_path / "src" / "pyspd" / "model.py").write_text("value = 2\n")
    second = python_execution_sha256(tmp_path)

    assert len(first) == 64
    assert first != second


def test_gams_execution_fingerprint_binds_source_and_executable(tmp_path) -> None:
    project = tmp_path / "project"
    source = tmp_path / "vspd"
    executable = tmp_path / "gams"
    (project / "src" / "pyspd").mkdir(parents=True)
    (project / "tools" / "gate12").mkdir(parents=True)
    (project / "tools" / "oracle").mkdir(parents=True)
    (project / "src" / "pyspd" / "model.py").write_text("model = 1\n")
    (project / "pyproject.toml").write_text("[project]\n")
    (project / "uv.lock").write_text("version = 1\n")
    (source / "Programs").mkdir(parents=True)
    (source / "Programs" / "vSPDmodel.gms").write_text("model source\n")
    executable.write_bytes(b"gams-runtime")

    first = gams_execution_sha256(source, executable, project)
    (source / "Programs" / "vSPDmodel.gms").write_text("changed source\n")
    second = gams_execution_sha256(source, executable, project)

    assert len(first) == 64
    assert first != second
