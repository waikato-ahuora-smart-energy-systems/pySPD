"""Repository-policy tests for the protected-main pull-request workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci-pull-request.yml"


def test_main_validation_is_pull_request_only() -> None:
    assert WORKFLOW.is_file(), "PR validation workflow is absent"
    content = WORKFLOW.read_text(encoding="utf-8")

    assert content.startswith("name: PR Validation\n")
    assert 'branches: ["main"]' in content
    assert "types: [opened, synchronize, reopened, ready_for_review]" in content
    assert "\n  push:" not in content
    assert "github.event.pull_request.draft == false" in content
    assert not (ROOT / ".github/workflows/quality.yml").exists()


def test_required_check_is_read_only_and_reproducible() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "  pr-gate:\n" in content
    assert "name: pr-gate" in content
    assert "timeout-minutes: 30" in content
    assert "permissions:\n  contents: read" in content
    assert "persist-credentials: false" in content
    assert "uv sync --frozen --group clp --group cbc --group docs" in content
    assert "uv run --no-sync ruff check ." in content
    assert "uv run --no-sync mypy src tools" in content
    assert "uv run --no-sync pytest -q" in content
    assert "uv run --no-sync python -m tools.probity_audit" in content
    assert "uv run --no-sync sphinx-build -W --keep-going -b html docs site" in content
    assert "git diff --check" in content
