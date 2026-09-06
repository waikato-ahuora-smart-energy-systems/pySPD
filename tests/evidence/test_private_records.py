from pathlib import Path

from pyspd.evidence import EvidenceArchiveBuilder
from tools.build_evidence_archives import build
from tools.evidence_paths import repository_evidence_path


def test_historical_record_paths_resolve_outside_user_docs(tmp_path: Path) -> None:
    for relative in (
        "docs/gate-4/tdd/logs/core-red.log",
        "docs/gate-12/cplex-reference-paths-example.jsonl",
        "docs/research/tdd/logs/evidence-externalization-red.log",
    ):
        destination = tmp_path / "private" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"retained evidence")
        assert repository_evidence_path(tmp_path, relative).read_bytes() == (
            b"retained evidence"
        )
    for relative in ("tests/fixtures/example.gdx", "private/docs/gate-4/new.json"):
        assert repository_evidence_path(tmp_path, relative) == tmp_path / relative
    absolute = tmp_path / "elsewhere.jsonl"
    assert repository_evidence_path(tmp_path, absolute) == absolute


def test_archive_bytes_survive_private_directory_move(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    relative = Path("docs/gate-12/cplex-reference-paths-example.json")
    original = root / relative
    original.parent.mkdir(parents=True)
    original.write_text('{"retained": true}\n')
    before = EvidenceArchiveBuilder(root).build(
        (relative,), tmp_path / "before.tar.gz"
    )
    relocated = root / "private" / relative
    relocated.parent.mkdir(parents=True)
    original.rename(relocated)
    for family in ("cplex_reference", "cplex_consecutive", "odd_day_reference"):
        fixture = root / "tests/fixtures" / family / "example.gdx"
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"fixture")

    manifest = build(
        root, tmp_path / "archives", release_base_url="https://example.invalid/v1"
    )
    after = manifest.artifact("gate12-solver-paths-v1")
    assert after.sha256 == before.sha256
    assert after.size_bytes == before.size_bytes
    assert after.file_count == 1
