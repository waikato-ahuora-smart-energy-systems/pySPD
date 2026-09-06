from pathlib import Path

import pytest


def require_external_evidence(path: Path, artifact_id: str) -> None:
    """Skip an oracle assertion until its hash-bound archive is restored."""

    if path.exists():
        return
    destination = "private" if artifact_id == "gate12-solver-paths-v1" else "."
    pytest.skip(
        "external validation evidence is not installed; run "
        f"`uv run pyspd evidence fetch {artifact_id} --destination {destination}`"
    )
