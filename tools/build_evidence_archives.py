"""Build deterministic external archives for PySPD's large oracle evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from pyspd.evidence import (
    EvidenceArchiveBuilder,
    EvidenceArtifact,
    EvidenceManifest,
)


@dataclass(frozen=True, slots=True)
class ArchivePlan:
    artifact_id: str
    filename: str
    description: str
    source_paths: tuple[Path, ...]
    archive_root: Path = Path(".")


class RepositoryEvidencePlan:
    """Select the version-one corpora without including regenerable outputs."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def plans(self) -> tuple[ArchivePlan, ...]:
        gate12_paths = tuple(
            path.relative_to(self.root / "private")
            for path in sorted(
                (self.root / "private/docs/gate-12").glob("cplex-reference-paths-*.json")
            )
        )
        return (
            ArchivePlan(
                "cplex-reference-v1",
                "pyspd-cplex-reference-v1.tar.gz",
                "Ten-day random CPLEX reference corpus with GDX inputs",
                (Path("tests/fixtures/cplex_reference"),),
            ),
            ArchivePlan(
                "cplex-consecutive-v1",
                "pyspd-cplex-consecutive-v1.tar.gz",
                "Five consecutive CPLEX reference days with GDX inputs",
                (Path("tests/fixtures/cplex_consecutive"),),
            ),
            ArchivePlan(
                "odd-day-reference-v1",
                "pyspd-odd-day-reference-v1.tar.gz",
                "Twelve odd-day inputs and six retained 2019 CPLEX result trees",
                (Path("tests/fixtures/odd_day_reference"),),
            ),
            ArchivePlan(
                "gate12-solver-paths-v1",
                "pyspd-gate12-solver-paths-v1.tar.gz",
                "Detailed Gate 12 SCIP-to-fixed-RMIP solver-path observations",
                gate12_paths,
                archive_root=Path("private"),
            ),
        )


def build(
    root: Path, output: Path, *, release_base_url: str
) -> EvidenceManifest:
    root = root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts: list[EvidenceArtifact] = []
    for plan in RepositoryEvidencePlan(root).plans():
        # Keep the v1 archive member names and bytes despite the repository move.
        builder = EvidenceArchiveBuilder(root / plan.archive_root)
        result = builder.build(plan.source_paths, output / plan.filename)
        artifacts.append(
            EvidenceArtifact(
                artifact_id=plan.artifact_id,
                version="1",
                url=f"{release_base_url.rstrip('/')}/{plan.filename}",
                sha256=result.sha256,
                size_bytes=result.size_bytes,
                description=plan.description,
                file_count=result.file_count,
                uncompressed_size_bytes=result.uncompressed_size_bytes,
            )
        )
    manifest = EvidenceManifest(schema_version=1, artifacts=tuple(artifacts))
    (output / "manifest-v1.json").write_text(
        json.dumps(manifest.to_dict(include_logical_sha256=True), indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--release-base-url",
        default=(
            "https://github.com/waikato-ahuora-smart-energy-systems/pySPD/"
            "releases/download/evidence-v1"
        ),
    )
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    manifest = build(
        arguments.root,
        arguments.output,
        release_base_url=arguments.release_base_url,
    )
    print(
        json.dumps(
            {
                "artifact_count": len(manifest.artifacts),
                "logical_sha256": manifest.logical_sha256,
                "output": str(arguments.output.resolve()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
