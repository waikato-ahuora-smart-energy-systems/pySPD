"""Deterministic source fingerprints for Gate 12 replay execution."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.gate12.evidence import EvidenceContractError


def python_execution_sha256(project_root: Path | None = None) -> str:
    """Hash every Python/runtime input that can alter candidate replay evidence."""

    root = (project_root or Path(__file__).parents[2]).resolve()
    paths = [root / "pyproject.toml", root / "uv.lock"]
    for source_directory in ("src/pyspd", "tools/gate12", "tools/oracle"):
        directory = root / source_directory
        paths.extend(directory.rglob("*.py"))
    files = sorted(
        (path for path in paths if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    required = {root / "pyproject.toml", root / "uv.lock"}
    if not required.issubset(files) or not files:
        raise EvidenceContractError(
            "REQ-G12-EXECUTION: candidate execution sources are incomplete"
        )
    digest = hashlib.sha256()
    for path in files:
        relative_bytes = path.relative_to(root).as_posix().encode()
        payload = path.read_bytes()
        digest.update(len(relative_bytes).to_bytes(8, "big"))
        digest.update(relative_bytes)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def gams_execution_sha256(
    source_tree: Path,
    gams_executable: Path,
    project_root: Path | None = None,
) -> str:
    """Bind the reference tooling, pinned GAMS source, and executable bytes."""

    source = source_tree.resolve()
    executable = gams_executable.resolve()
    if not source.is_dir() or not executable.is_file():
        raise EvidenceContractError(
            "REQ-G12-EXECUTION: GAMS execution sources are incomplete"
        )
    files: list[tuple[str, Path]] = [("runtime/gams", executable)]
    for directory_name in ("Programs", "Override", "vSPD_Overrides"):
        directory = source / directory_name
        if not directory.is_dir():
            continue
        files.extend(
            (f"source/{path.relative_to(source).as_posix()}", path)
            for path in directory.rglob("*")
            if path.is_file()
        )
    if len(files) == 1:
        raise EvidenceContractError(
            "REQ-G12-EXECUTION: pinned GAMS source tree is empty"
        )
    digest = hashlib.sha256()
    python_hash = python_execution_sha256(project_root).encode()
    digest.update(len(python_hash).to_bytes(8, "big"))
    digest.update(python_hash)
    for name, path in sorted(files):
        encoded_name = name.encode()
        payload = path.read_bytes()
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
