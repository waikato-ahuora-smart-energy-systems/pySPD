from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from pyspd.evidence import (
    EvidenceArchiveBuilder,
    EvidenceArtifact,
    EvidenceError,
    EvidenceManifest,
    EvidenceStore,
)


def _archive(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, payload in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = 0
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))


def _artifact(archive: Path, *, digest: str | None = None) -> EvidenceArtifact:
    return EvidenceArtifact(
        artifact_id="oracle-mini",
        version="1",
        url=archive.as_uri(),
        sha256=digest or hashlib.sha256(archive.read_bytes()).hexdigest(),
        size_bytes=archive.stat().st_size,
        description="tiny deterministic oracle fixture",
    )


def test_manifest_is_canonical_and_rejects_duplicate_ids(tmp_path: Path) -> None:
    archive = tmp_path / "oracle-mini.tar.gz"
    _archive(archive, {"tests/fixtures/oracle-mini/result.txt": b"gold\n"})
    artifact = _artifact(archive)
    manifest = EvidenceManifest(schema_version=1, artifacts=(artifact,))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")

    loaded = EvidenceManifest.from_json(path)

    assert loaded == manifest
    assert loaded.logical_sha256 == manifest.logical_sha256
    with pytest.raises(EvidenceError, match="duplicate artifact id"):
        EvidenceManifest(schema_version=1, artifacts=(artifact, artifact))


def test_fetch_verifies_hash_and_rehydrates_idempotently(tmp_path: Path) -> None:
    archive = tmp_path / "oracle-mini.tar.gz"
    payload = b"validated evidence\n"
    _archive(archive, {"tests/fixtures/oracle-mini/result.txt": payload})
    artifact = _artifact(archive)
    store = EvidenceStore(tmp_path / "cache")
    destination = tmp_path / "checkout"

    first = store.fetch(artifact, destination=destination)
    second = store.fetch(artifact, destination=destination)

    assert first.archive_path == second.archive_path
    assert first.downloaded is True
    assert second.downloaded is False
    assert first.extracted_files == (Path("tests/fixtures/oracle-mini/result.txt"),)
    assert (destination / first.extracted_files[0]).read_bytes() == payload
    assert store.verify(artifact) == first.archive_path


def test_fetch_fails_closed_on_hash_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "oracle-mini.tar.gz"
    _archive(archive, {"result.txt": b"changed"})
    artifact = _artifact(archive, digest="0" * 64)
    store = EvidenceStore(tmp_path / "cache")

    with pytest.raises(EvidenceError, match="SHA-256 mismatch"):
        store.fetch(artifact, destination=tmp_path / "checkout")

    assert not tuple((tmp_path / "cache").glob("*.tar.gz"))


def test_extraction_rejects_paths_outside_destination(tmp_path: Path) -> None:
    archive = tmp_path / "malicious.tar.gz"
    _archive(archive, {"../escape.txt": b"no"})
    artifact = _artifact(archive)

    with pytest.raises(EvidenceError, match="unsafe archive member"):
        EvidenceStore(tmp_path / "cache").fetch(
            artifact, destination=tmp_path / "checkout"
        )

    assert not (tmp_path / "escape.txt").exists()


def test_archive_builder_is_deterministic_and_preserves_relative_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    (root / "evidence/day").mkdir(parents=True)
    (root / "evidence/day/result.csv").write_text("value\n1\n", encoding="utf-8")
    (root / "evidence/manifest.json").write_text("{}\n", encoding="utf-8")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    builder = EvidenceArchiveBuilder(root)

    first_result = builder.build((Path("evidence"),), first)
    second_result = builder.build((Path("evidence"),), second)

    assert first.read_bytes() == second.read_bytes()
    assert first_result.sha256 == second_result.sha256
    assert first_result.file_count == 2
    assert first_result.uncompressed_size_bytes == len(b"value\n1\n") + len(b"{}\n")
    with tarfile.open(first, "r:gz") as archive:
        assert tuple(member.name for member in archive.getmembers()) == (
            "evidence/day/result.csv",
            "evidence/manifest.json",
        )
