from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

CORPUS = Path(__file__).parents[1] / "fixtures" / "odd_day_reference"


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


def test_odd_day_reference_corpus_is_complete_and_hash_bound() -> None:
    if not (CORPUS / "2019").is_dir():
        pytest.skip("odd-day-reference-v1 external evidence is not installed")
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["profile"] == "pyspd-odd-day-reference-corpus-v2"
    assert len(manifest["days"]) == 12
    assert [day["year"] for day in manifest["days"]].count(2019) == 6
    assert [day["year"] for day in manifest["days"]].count(2022) == 6

    for day in manifest["days"]:
        input_path = CORPUS / day["input"]
        assert input_path.stat().st_size == day["input_bytes"]
        assert _sha256(input_path) == day["input_sha256"]

        results = input_path.parent.parent / "results"
        if day["reference_kind"] != "archived-cplex-results":
            assert not results.exists()
            continue
        result_files = tuple(results.iterdir())
        assert len(result_files) == day["result_file_count"]
        assert sum(path.stat().st_size for path in result_files) == day["result_bytes"]
        assert _result_tree_sha256(results) == day["result_tree_sha256"]


def test_odd_2019_cplex_summary_rows_report_success() -> None:
    if not (CORPUS / "2019").is_dir():
        pytest.skip("odd-day-reference-v1 external evidence is not installed")
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))

    for day in manifest["days"]:
        if day["reference_kind"] != "archived-cplex-results":
            continue
        input_path = CORPUS / day["input"]
        summaries = tuple((input_path.parent.parent / "results").glob("*Summary*"))
        assert len(summaries) == 1
        with summaries[0].open(newline="", encoding="utf-8-sig") as handle:
            rows = tuple(csv.DictReader(handle))
        assert len(rows) == day["summary_rows"]
        assert all(float(row["SolveStatus (1=OK)"]) == 1.0 for row in rows)
