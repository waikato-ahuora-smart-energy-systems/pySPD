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
    assert (
        "types: [opened, synchronize, reopened, ready_for_review, edited, labeled, unlabeled]"
        in content
    )
    assert "\n  push:" not in content
    assert "github.event.pull_request.draft == false" in content
    assert not (ROOT / ".github/workflows/quality.yml").exists()


def test_required_check_is_read_only_and_reproducible() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "  pr-gate:\n" in content
    assert "name: pr-gate" in content
    assert "timeout-minutes: 30" in content
    assert "permissions:\n  contents: read" in content
    gate = content.split("  pr-gate:\n", 1)[1].split(
        "  record-bumped-validation:\n", 1
    )[0]
    assert "permissions:" not in gate  # Inherits only contents: read.
    assert "persist-credentials: false" in content
    assert "uv sync --frozen --group clp --group cbc --group docs" in content
    assert "uv run --no-sync ruff check ." in content
    assert "uv run --no-sync mypy src tools" in content
    assert "uv run --no-sync pytest -q" in content
    assert "uv run --no-sync python -m tools.probity_audit" in content
    assert "uv run --no-sync sphinx-build -W --keep-going -b html docs site" in content
    assert "git diff --check" in content


def test_bumped_commit_is_validated_and_reported_without_token_push_recursion() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    assert "cancel-in-progress: false" in content
    assert "needs: bump-version" in content
    assert "ref: ${{ needs.bump-version.outputs.sha || github.sha }}" in content
    assert 'run: test "${BUMP_RESULT}" = success' in content
    assert "needs: [bump-version, pr-gate]" in content
    assert '-f name=pr-gate -f head_sha="${TESTED_SHA}"' in content
    assert "github.event.pull_request.head.repo.full_name == github.repository" in content


def test_main_tags_explicitly_dispatch_qualified_publication() -> None:
    content = (ROOT / ".github/workflows/publish-pypi.yml").read_text()
    assert 'branches: ["main"]' in content
    assert "BASE_SHA: ${{ github.event.before }}" in content
    assert 'gh workflow run publish-pypi.yml --ref "${tag}"' in content
    assert 'test "$(git rev-parse "refs/tags/${tag}^{commit}")" = "${GITHUB_SHA}"' in content
    assert 'check --tag "${RELEASE_TAG}"' in content
    assert '--expected-version "${RELEASE_VERSION}"' in content
    assert "needs: [qualify, publish]" in content
    assert "--verify-tag --generate-notes" in content
