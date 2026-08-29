"""Run deterministic preprocessing invariants across the governed daily corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections import Counter
from pathlib import Path

from pyspd.contracts import CaseData, CaseIdentifier
from pyspd.data import CanonicalFeed
from pyspd.preprocess import Vspd506Preprocessor, validate_preprocessing_invariants


def _logical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def qualify(corpus_root: Path) -> dict[str, object]:
    sources = sorted(path for path in corpus_root.iterdir() if path.is_dir())
    if not sources:
        raise ValueError(f"no canonical feeds in {corpus_root}")
    preprocessor = Vspd506Preprocessor()
    cases: list[dict[str, object]] = []
    invariant_totals: Counter[str] = Counter()
    total_violations = 0
    for source_index, path in enumerate(sources, start=1):
        feed = CanonicalFeed.open(path)
        definitions = feed.read_symbol("i_caseDefn").records
        selected = (definitions[0], definitions[-1])
        for position, definition in zip(("first", "last"), selected, strict=True):
            case_id = definition.keys[0]
            raw = feed.read_case(case_id)
            period_records = raw["i_dateTimeTradePeriodMap"].records
            if len(period_records) != 1:
                raise ValueError(
                    f"{path.name}/{case_id}: expected one trading-period mapping"
                )
            _, datetime, trading_period = period_records[0].keys
            case_data = CaseData(
                "vspd-v5.0.6",
                CaseIdentifier(case_id, datetime, trading_period),
                raw,
            )
            first = preprocessor.transform(case_data)
            repeated = preprocessor.transform(case_data)
            deterministic = (
                first.structural_signature == repeated.structural_signature
                and tuple(item.logical_sha256 for item in first.checkpoints)
                == tuple(item.logical_sha256 for item in repeated.checkpoints)
            )
            invariants = validate_preprocessing_invariants(first)
            for check in invariants.checks:
                invariant_totals[check.name] += check.observations
                total_violations += len(check.violations)
            cases.append(
                {
                    "source": path.name,
                    "selection": position,
                    "case_id": case_id,
                    "datetime": datetime,
                    "trading_period": trading_period,
                    "deterministic": deterministic,
                    "structural_signature": first.structural_signature,
                    "checkpoint_hashes": {
                        item.step: item.logical_sha256 for item in first.checkpoints
                    },
                    "invariant_hash": invariants.logical_sha256,
                    "invariants_passed": invariants.passed,
                    "domain_counts": {
                        "nodes": len(first.set("node").members),
                        "buses": len(first.set("bus").members),
                        "branches": len(first.set("branch").members),
                        "offers": len(first.set("offer").members),
                        "bids": len(first.set("bid").members),
                    },
                }
            )
        if source_index % 10 == 0 or source_index == len(sources):
            print(
                f"qualified {source_index}/{len(sources)} feeds ({len(cases)} cases)",
                flush=True,
            )
    nondeterministic = sum(not bool(case["deterministic"]) for case in cases)
    failed_invariants = sum(not bool(case["invariants_passed"]) for case in cases)
    source_bindings = [
        {
            "source": path.name,
            "feed_logical_sha256": CanonicalFeed.open(path).logical_sha256,
            "raw_gdx_sha256": CanonicalFeed.open(path).source_sha256,
        }
        for path in sources
    ]
    case_digest = _logical_sha256(cases)
    passed = (
        len(sources) == 139
        and len(cases) == 278
        and nondeterministic == 0
        and failed_invariants == 0
        and total_violations == 0
    )
    return {
        "schema_version": 1,
        "profile": "vspd-v5.0.6",
        "scope": {
            "source": "Gate 2 governed 139-daily-GDX canonical corpus",
            "selection": "chronological first and last case from every daily feed",
            "daily_feeds": len(sources),
            "cases": len(cases),
        },
        "execution_profile": {
            "platform": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "linux_x86_64": "deferred-by-user-direction",
        },
        "source_bindings": source_bindings,
        "invariant_observations": dict(sorted(invariant_totals.items())),
        "total_invariant_violations": total_violations,
        "nondeterministic_cases": nondeterministic,
        "failed_invariant_cases": failed_invariants,
        "case_evidence_logical_sha256": case_digest,
        "cases": cases,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = qualify(args.corpus_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "feeds": report["scope"]["daily_feeds"],  # type: ignore[index]
                "cases": report["scope"]["cases"],  # type: ignore[index]
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
