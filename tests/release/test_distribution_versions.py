from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.qualify_distribution import inspect_artifacts


def make_archives(root: Path, changed: str = "") -> None:
    metadata = (
        "Metadata-Version: 2.4\nName: pySPD\nVersion: 1.2.3\n"
        "License-Expression: Apache-2.0\nLicense-File: LICENSE\n"
        "Requires-Dist: pyscipopt\nRequires-Dist: highspy\n"
        "Provides-Extra: gdx\nProvides-Extra: clp\nProvides-Extra: cbc\n\n"
    )
    lock = (
        'version = 1\n[[package]]\nname = "pyspd"\nversion = "1.2.3"\n'
        'source = { editable = "." }\n'
    )
    wheel_files = {
        "pyspd-1.2.3.dist-info/METADATA": metadata,
        "pyspd-1.2.3.dist-info/licenses/LICENSE": "Apache License",
        "pyspd/__init__.py": '__version__ = "1.2.3"\n',
        "pyspd/_build/uv.lock": lock,
    }
    source_files = {
        "PKG-INFO": metadata,
        "LICENSE": "Apache License",
        "src/pyspd/__init__.py": '__version__ = "1.2.3"\n',
        "pyproject.toml": '[project]\nname = "pySPD"\nversion = "1.2.3"\n',
        "uv.lock": lock,
    }
    for files in (wheel_files, source_files):
        if changed in files:
            files[changed] = files[changed].replace("1.2.3", "1.2.2")
    with zipfile.ZipFile(root / "pyspd-1.2.3-py3-none-any.whl", "w") as wheel:
        for name, text in wheel_files.items():
            wheel.writestr(name, text)
    with tarfile.open(root / "pyspd-1.2.3.tar.gz", "w:gz") as source:
        for name, text in source_files.items():
            data = text.encode()
            member = tarfile.TarInfo(f"pyspd-1.2.3/{name}")
            member.size = len(data)
            source.addfile(member, io.BytesIO(data))


def test_qualified_artifacts_share_the_release_version(tmp_path) -> None:
    make_archives(tmp_path)
    assert inspect_artifacts(tmp_path, "1.2.3")["version"] == "1.2.3"


@pytest.mark.parametrize(
    "changed",
    [
        "pyspd-1.2.3.dist-info/METADATA",
        "pyspd/__init__.py",
        "pyspd/_build/uv.lock",
        "PKG-INFO",
        "src/pyspd/__init__.py",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_mismatched_distribution_versions_are_rejected(tmp_path, changed) -> None:
    make_archives(tmp_path, changed)
    with pytest.raises(ValueError, match="differ"):
        inspect_artifacts(tmp_path, "1.2.3")


def test_archives_must_match_the_release_tag_version(tmp_path) -> None:
    make_archives(tmp_path)
    with pytest.raises(ValueError, match="release tag"):
        inspect_artifacts(tmp_path, "1.2.4")
