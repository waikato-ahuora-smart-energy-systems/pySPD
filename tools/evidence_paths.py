"""Locate historical evidence after its move outside the documentation site."""

from pathlib import Path


def repository_evidence_path(root: Path, path: str | Path) -> Path:
    """Resolve retained docs/gate-* and docs/research paths without editing records."""
    relative = Path(path)
    if (
        not relative.is_absolute()
        and len(relative.parts) >= 2
        and relative.parts[0] == "docs"
        and (
            relative.parts[1].startswith("gate-")
            or relative.parts[1] == "research"
        )
    ):
        return root / "private" / relative
    return root / relative
