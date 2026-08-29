"""Resumable qualification of raw GDX inputs into canonical feeds."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyspd.data import (
    CanonicalFeed,
    GdxAdapter,
    SymbolCatalog,
    V5InputValidator,
)


@dataclass(frozen=True, slots=True)
class CorpusQualifier:
    converter: Callable[[Path, Path], CanonicalFeed]

    def run(
        self,
        *,
        inventory_path: Path,
        input_root: Path,
        output_root: Path,
        evidence_path: Path,
        limit: int | None = None,
    ) -> dict[str, Any]:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        artifacts = list(inventory["artifacts"])
        if inventory["artifact_count"] != len(artifacts):
            raise ValueError("inventory artifact_count does not match artifacts")
        if limit is not None:
            artifacts = artifacts[:limit]
        output_root.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        for position, artifact in enumerate(artifacts, start=1):
            trading_date = artifact["trading_date"]
            source = (
                input_root
                / trading_date[:4]
                / f"Pricing_{trading_date}.gdx"
            )
            if source.stat().st_size != artifact["size_bytes"]:
                raise ValueError(f"raw size mismatch for {trading_date}")
            actual_sha = self._file_sha256(source)
            if actual_sha != artifact["sha256"]:
                raise ValueError(f"raw SHA-256 mismatch for {trading_date}")

            destination = output_root / trading_date
            if destination.exists():
                feed = CanonicalFeed.open(destination)
                if feed.source_sha256 != actual_sha:
                    raise ValueError(f"existing feed source mismatch for {trading_date}")
            else:
                partial = output_root / f"{trading_date}.partial"
                if partial.exists():
                    raise ValueError(
                        f"stale partial feed requires inspection: {partial}"
                    )
                self.converter(source, partial)
                partial.rename(destination)
                feed = CanonicalFeed.open(destination)

            SymbolCatalog.vspd_v5().validate(feed.read_schema())
            definitions = feed.read_symbol("i_caseDefn").records
            case_ids = list(
                dict.fromkeys(
                    record.keys[0]
                    for record in (
                        definitions[:1] + definitions[-1:] if definitions else ()
                    )
                )
            )
            representatives: list[dict[str, Any]] = []
            for case_id in case_ids:
                case = feed.read_case(case_id)
                report = V5InputValidator().validate(case)
                report.raise_for_errors()
                representatives.append(
                    {
                        "case_id": case_id,
                        "record_count": sum(
                            len(symbol.records) for symbol in case.symbols
                        ),
                        "logical_sha256": case.logical_sha256,
                        "semantic_validation_passed": True,
                    }
                )
            entries.append(
                {
                    "trading_date": trading_date,
                    "input_size_bytes": artifact["size_bytes"],
                    "input_sha256": actual_sha,
                    "feed_logical_sha256": feed.logical_sha256,
                    "symbol_count": len(feed.symbol_names),
                    "record_count": sum(feed.symbol_record_counts.values()),
                    "representative_cases": representatives,
                    "status": "qualified",
                }
            )
            print(
                f"[{position}/{len(artifacts)}] {trading_date} qualified",
                flush=True,
            )
        payload: dict[str, Any] = {
            "schema_version": 1,
            "inventory": inventory_path.name,
            "inventory_sha256": self._file_sha256(inventory_path),
            "declared_input_count": inventory["artifact_count"],
            "qualified_input_count": len(entries),
            "entries": entries,
        }
        payload["logical_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = evidence_path.with_suffix(evidence_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(evidence_path)
        return payload

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--gams-system-directory", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    qualifier = CorpusQualifier(
        lambda source, destination: GdxAdapter.write_feed(
            source,
            destination,
            system_directory=arguments.gams_system_directory,
        )
    )
    qualifier.run(
        inventory_path=arguments.inventory,
        input_root=arguments.input_root,
        output_root=arguments.output_root,
        evidence_path=arguments.evidence,
        limit=arguments.limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
