from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

CORPUS = Path(__file__).parents[1] / "fixtures" / "cplex_consecutive"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(path.iterdir(), key=lambda item: item.name.encode()):
        digest.update(child.name.encode())
        digest.update(b"\0")
        digest.update(_sha256(child).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def test_consecutive_cplex_corpus_is_complete_successful_and_hash_bound() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["profile"] == "pyspd-cplex-consecutive-clean-streak-v1"
    assert [day["date"] for day in manifest["days"]] == [
        "2023-09-23",
        "2023-09-24",
        "2023-09-25",
        "2023-09-26",
    ]
    for day in manifest["days"]:
        input_path = CORPUS / day["input"]
        results = input_path.parent.parent / "results"
        result_files = tuple(results.iterdir())
        summaries = tuple(results.glob("*SummaryResults_TP.csv"))

        assert input_path.stat().st_size == day["input_bytes"]
        assert _sha256(input_path) == day["input_sha256"]
        assert len(result_files) == day["result_file_count"]
        assert sum(path.stat().st_size for path in result_files) == day["result_bytes"]
        assert _result_tree_sha256(results) == day["result_tree_sha256"]
        assert len(summaries) == 1
        with summaries[0].open(newline="", encoding="utf-8-sig") as handle:
            rows = tuple(csv.DictReader(handle))
        assert len(rows) == day["summary_rows"]
        assert all(float(row["SolveStatus (1=OK)"]) == 1.0 for row in rows)
