"""Build the preregistered historical stress-event atlas from retained results."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pyspd.studies import (
    AtlasCorpusLoader,
    AtlasThresholds,
    StressEventAtlasBuilder,
    StressEventAtlasWriter,
    file_sha256,
)

DEFAULT_PREREGISTRATION = Path(
    "docs/case-studies/evidence/historical-stress-event-atlas-v1/preregistration.json"
)


def build(preregistration_path: Path, *, root: Path) -> tuple[Path, ...]:
    root = root.resolve()
    config_path = (
        preregistration_path
        if preregistration_path.is_absolute()
        else root / preregistration_path
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("status") != "preregistered-before-classification":
        raise ValueError("atlas configuration is not a preregistered definition")
    manifests = tuple(root / Path(path) for path in config["source_manifests"])
    thresholds = AtlasThresholds(**config["thresholds"])
    sources = AtlasCorpusLoader().load(manifests)
    atlas = StressEventAtlasBuilder(thresholds).build(
        sources,
        verify_hashes=True,
        preregistration_sha256=file_sha256(config_path),
    )
    output_directory = root / Path(config["output_directory"])
    return StressEventAtlasWriter().write(atlas, output_directory)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    outputs = build(arguments.preregistration, root=arguments.root)
    print("\n".join(str(path) for path in outputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
