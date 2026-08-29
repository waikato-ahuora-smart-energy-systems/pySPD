from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_package_metadata_has_readme_and_uv_cli() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["readme"] == "README.md"
    assert project["project"]["scripts"]["pyspd"] == "pyspd.cli:entrypoint"
    assert (ROOT / "README.md").is_file()


def test_ci_matches_linux_execution_deferral() -> None:
    workflow = (ROOT / ".github/workflows/quality.yml").read_text()
    assert "ubuntu-latest" not in workflow
    assert "macos-latest" in workflow
    assert "uv sync --frozen" in workflow
    assert "pip install" not in workflow
