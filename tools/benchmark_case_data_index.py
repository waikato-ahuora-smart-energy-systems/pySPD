"""Benchmark indexed versus repeated-scan extraction of daily GDX cases."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import SymbolCatalog
from pyspd.data.gdx import GdxAdapter
from pyspd.data.raw import RawSymbol, RawSymbols
from pyspd.orchestration import DailyCase, DailyCaseDataIndex, DailyCaseSelector
from tools.gate12.execution_provenance import python_execution_sha256

_SOURCE_PROFILE = "vspd-v5.0.6"


@dataclass(frozen=True, slots=True)
class ExtractionRun:
    mode: str
    repetition: int
    seconds: float
    extracted_record_count: int


class LegacyCaseDataScanner:
    """Retain the pre-index extraction algorithm as a benchmark control."""

    def __init__(self, symbols: RawSymbols) -> None:
        self._symbols = symbols

    def case_data(self, selected: DailyCase) -> CaseData:
        case_symbols = []
        for symbol in self._symbols.symbols:
            records = symbol.records
            if symbol.domains and symbol.domains[0] in {"ca", "caseID"}:
                records = tuple(
                    record
                    for record in records
                    if record.keys[0] == selected.case_id
                )
            case_symbols.append(_with_records(symbol, records))
        return _case_data(self._symbols, selected, tuple(case_symbols))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--system-directory", required=True, type=Path)
    parser.add_argument("--case-count", type=int, default=24)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.case_count <= 0 or args.repetitions <= 0:
        parser.error("case-count and repetitions must be positive")

    source_started = time.perf_counter()
    symbols = GdxAdapter.read(args.input, system_directory=args.system_directory)
    SymbolCatalog.vspd_v5().validate(symbols)
    source_seconds = time.perf_counter() - source_started
    selected = DailyCaseSelector().select(symbols)[: args.case_count]
    if len(selected) != args.case_count:
        parser.error(
            f"requested {args.case_count} cases but source contains {len(selected)}"
        )

    runs: list[ExtractionRun] = []
    first_results: dict[str, tuple[CaseData, ...]] = {}
    for repetition in range(1, args.repetitions + 1):
        order = ("scan", "index") if repetition % 2 else ("index", "scan")
        for mode in order:
            gc.collect()
            started = time.perf_counter()
            if mode == "scan":
                scanner = LegacyCaseDataScanner(symbols)
                results = tuple(scanner.case_data(item) for item in selected)
            else:
                index = DailyCaseDataIndex(
                    symbols,
                    case_ids=tuple(item.case_id for item in selected),
                )
                results = tuple(index.case_data(item) for item in selected)
            seconds = time.perf_counter() - started
            record_count = sum(
                len(symbol.records)
                for case in results
                for symbol in case.symbols.symbols
            )
            runs.append(ExtractionRun(mode, repetition, seconds, record_count))
            first_results.setdefault(mode, results)
            if repetition > 1:
                del results

    scan = first_results["scan"]
    indexed = first_results["index"]
    exact_matches = tuple(left == right for left, right in zip(scan, indexed, strict=True))
    scan_seconds = [run.seconds for run in runs if run.mode == "scan"]
    index_seconds = [run.seconds for run in runs if run.mode == "index"]
    scan_median = statistics.median(scan_seconds)
    index_median = statistics.median(index_seconds)
    unsigned: dict[str, Any] = {
        "schema_version": 1,
        "profile": "pyspd-daily-case-data-index-benchmark-v1",
        "source_name": args.input.name,
        "source_sha256": _file_sha256(args.input),
        "source_load_and_catalog_seconds": source_seconds,
        "environment": f"{platform.system()}-{platform.machine()}",
        "execution_sha256": python_execution_sha256(),
        "benchmark_sha256": _file_sha256(Path(__file__)),
        "case_count": len(selected),
        "case_ids": [item.case_id for item in selected],
        "case_scoped_source_record_count": sum(
            len(symbol.records)
            for symbol in symbols.symbols
            if symbol.domains and symbol.domains[0] in {"ca", "caseID"}
        ),
        "repetitions": args.repetitions,
        "runs": [
            {
                "mode": run.mode,
                "repetition": run.repetition,
                "seconds": run.seconds,
                "extracted_record_count": run.extracted_record_count,
            }
            for run in runs
        ],
        "summary": {
            "scan_median_seconds": scan_median,
            "index_median_seconds": index_median,
            "speedup_factor": scan_median / index_median,
            "elapsed_reduction_percent": 100.0
            * (scan_median - index_median)
            / scan_median,
        },
        "parity": {
            "exact_case_data_match": all(exact_matches),
            "matched_case_count": sum(exact_matches),
            "record_counts_match": all(
                run.extracted_record_count == runs[0].extracted_record_count
                for run in runs
            ),
        },
    }
    payload = {**unsigned, "logical_sha256": _logical_sha256(unsigned)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary": payload["summary"],
                "parity": payload["parity"],
                "logical_sha256": payload["logical_sha256"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _with_records(symbol: RawSymbol, records: tuple[Any, ...]) -> RawSymbol:
    return RawSymbol(
        symbol.name,
        symbol.symbol_type,
        symbol.dimension,
        symbol.domains,
        symbol.description,
        symbol.uel_orders,
        records,
    )


def _case_data(
    symbols: RawSymbols,
    selected: DailyCase,
    case_symbols: tuple[RawSymbol, ...],
) -> CaseData:
    return CaseData(
        _SOURCE_PROFILE,
        CaseIdentifier(
            selected.case_id, selected.date_time, selected.trading_period
        ),
        RawSymbols(symbols.source_name, symbols.source_sha256, case_symbols),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


if __name__ == "__main__":
    main()
