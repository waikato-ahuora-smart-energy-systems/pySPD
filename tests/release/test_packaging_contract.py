from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_package_metadata_has_readme_and_uv_cli() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["readme"] == "README.md"
    assert project["project"]["scripts"]["pyspd"] == "pyspd.cli:entrypoint"
    assert (ROOT / "README.md").is_file()


def test_read_the_docs_uses_native_uv_installation() -> None:
    configuration = (ROOT / ".readthedocs.yaml").read_text()

    assert "method: uv" in configuration
    assert "command: sync" in configuration
    assert "      groups:\n        - docs" in configuration
    assert "pip install" not in configuration
    assert "sphinx:\n  configuration: docs/conf.py" in configuration
    assert "fail_on_warning: true" in configuration
    assert not (ROOT / "mkdocs.yml").exists()


def test_ci_matches_linux_execution_deferral() -> None:
    workflow = (ROOT / ".github/workflows/ci-pull-request.yml").read_text()
    assert "ubuntu-latest" not in workflow
    assert "macos-latest" in workflow
    assert 'PYTHON_VERSION: "3.13"' in workflow
    assert "uv sync --frozen" in workflow
    assert "pip install" not in workflow
    assert 'branches: ["main"]' in workflow
    assert "cancel-in-progress: false" in workflow
    assert "timeout-minutes: 30" in workflow
