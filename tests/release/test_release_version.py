from __future__ import annotations

from pathlib import Path

import pytest

from tools.release_version import (
    RELEASE_FILES,
    bump_release,
    check_versions,
    next_version,
    parse_version,
    requested_part,
)


@pytest.mark.parametrize(
    ("labels", "title", "expected"),
    [
        ([], "Fix branding", "patch"),
        (["minor"], "New feature", "minor"),
        (["minor", "MAJOR"], "New API", "major"),
        ([], "[major] New API", "major"),
        ([], "[MiNoR] New feature", "minor"),
        (["patch"], "[major] Label takes precedence", "patch"),
        (["not-major"], "Minor wording fix", "patch"),
    ],
)
def test_bump_controls_match_openpinch(labels, title, expected) -> None:
    assert requested_part(labels, title) == expected


@pytest.mark.parametrize(
    ("current", "base", "part", "expected"),
    [
        ("0.1.0", "0.1.0", "patch", "0.1.1"),
        ("1.2.9", "1.2.9", "minor", "1.3.0"),
        ("1.2.9", "1.2.9", "major", "2.0.0"),
        ("1.2.10", "1.2.9", "patch", "1.2.10"),
        ("1.2.10", "1.2.9", "minor", "1.3.0"),
        ("2.0.0", "1.2.9", "patch", "2.0.0"),
    ],
)
def test_bumps_are_idempotent_and_reset_lower_components(
    current, base, part, expected
) -> None:
    assert next_version(current, base, part) == expected


@pytest.mark.parametrize("value", ["v1.2.3", "1.2", "01.2.3", "1.2.3rc1", "1.2.3\n"])
def test_invalid_release_versions_are_rejected(value) -> None:
    with pytest.raises(ValueError, match="stable"):
        parse_version(value)


def test_behind_main_is_rejected() -> None:
    with pytest.raises(ValueError, match="behind main"):
        next_version("0.1.0", "0.1.1", "patch")


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    (tmp_path / "src/pyspd").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pySPD"\nversion = "1.2.3"\n'
        '[tool.example]\nversion = "1.2.3"\n'
    )
    (tmp_path / "src/pyspd/__init__.py").write_text('__version__ = "1.2.3"\n')
    (tmp_path / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "dependency"\nversion = "1.2.3"\n'
        '[[package]]\nname = "pyspd"\nversion = "1.2.3"\n'
        'source = { editable = "." }\n'
    )
    (tmp_path / "README.md").write_text(
        "[Docs](https://github.com/org/pySPD/blob/v1.2.3/docs/index.md)\n"
    )
    (tmp_path / "docs/getting-started.md").write_text(
        'pip install "pyspd-1.2.3-py3-none-any.whl[gdx]"\n'
    )
    return tmp_path


def test_bump_updates_release_files_without_changing_dependencies(release_tree) -> None:
    assert bump_release(release_tree, "1.2.3", "minor") == "1.3.0"
    assert check_versions(release_tree, tag="v1.3.0") == "1.3.0"
    assert 'name = "dependency"\nversion = "1.2.3"' in (
        release_tree / "uv.lock"
    ).read_text()
    assert '[tool.example]\nversion = "1.2.3"' in (
        release_tree / "pyproject.toml"
    ).read_text()
    assert "/blob/v1.3.0/" in (release_tree / "README.md").read_text()
    assert "pyspd-1.3.0-" in (release_tree / "docs/getting-started.md").read_text()
    before = {name: (release_tree / name).read_bytes() for name in RELEASE_FILES}
    assert bump_release(release_tree, "1.2.3", "minor") == "1.3.0"
    assert before == {name: (release_tree / name).read_bytes() for name in RELEASE_FILES}


def test_mismatched_versions_do_not_partially_update_files(release_tree) -> None:
    (release_tree / "src/pyspd/__init__.py").write_text('__version__ = "9.0.0"\n')
    before = {name: (release_tree / name).read_bytes() for name in RELEASE_FILES}
    with pytest.raises(ValueError, match="versions differ"):
        bump_release(release_tree, "1.2.3", "patch")
    assert before == {name: (release_tree / name).read_bytes() for name in RELEASE_FILES}


def test_release_tag_must_match_package(release_tree) -> None:
    with pytest.raises(ValueError, match="release tag"):
        check_versions(release_tree, tag="v1.2.4")


def test_repository_versions_agree() -> None:
    check_versions(Path(__file__).resolve().parents[2])
