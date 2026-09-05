from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

from pyspd.cli import main


def _manifest(tmp_path: Path) -> Path:
    archive = tmp_path / "mini.tar.gz"
    payload = b"oracle\n"
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as handle:
        info = tarfile.TarInfo("evidence/result.txt")
        info.size = len(payload)
        info.mtime = 0
        handle.addfile(info, io.BytesIO(payload))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifacts": [
                    {
                        "artifact_id": "mini",
                        "version": "1",
                        "url": archive.as_uri(),
                        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                        "size_bytes": archive.stat().st_size,
                        "description": "CLI fixture",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_evidence_list_and_fetch_commands(tmp_path: Path, capsys) -> None:
    manifest = _manifest(tmp_path)
    cache = tmp_path / "cache"
    destination = tmp_path / "checkout"

    assert main(["evidence", "list", "--manifest", str(manifest)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["artifacts"][0]["artifact_id"] == "mini"

    assert (
        main(
            [
                "evidence",
                "fetch",
                "mini",
                "--manifest",
                str(manifest),
                "--cache",
                str(cache),
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    fetched = json.loads(capsys.readouterr().out)
    assert fetched["verified"] is True
    assert (destination / "evidence/result.txt").read_text() == "oracle\n"


def test_evidence_unknown_id_is_a_cli_error(tmp_path: Path, capsys) -> None:
    manifest = _manifest(tmp_path)

    assert (
        main(
            [
                "evidence",
                "verify",
                "missing",
                "--manifest",
                str(manifest),
                "--cache",
                str(tmp_path / "cache"),
            ]
        )
        == 2
    )
    assert "unknown evidence artifact" in capsys.readouterr().out
