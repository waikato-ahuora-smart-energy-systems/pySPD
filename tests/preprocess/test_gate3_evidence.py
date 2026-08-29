import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_gams_checkpoint_parity_has_zero_discrepancies() -> None:
    evidence = json.loads(
        (ROOT / "docs/gate-3/oracle-parity.json").read_text(encoding="utf-8")
    )

    assert evidence["passed"] is True
    assert evidence["comparison_count"] == 64
    assert all(item["passed"] for item in evidence["comparisons"])
    assert sum(item["missing_in_python"] for item in evidence["comparisons"]) == 0
    assert sum(item["extra_in_python"] for item in evidence["comparisons"]) == 0
    assert sum(item["value_mismatches"] for item in evidence["comparisons"]) == 0
    assert (
        max(item["maximum_absolute_error"] for item in evidence["comparisons"]) == 0.0
    )


def test_governed_corpus_invariants_and_determinism_pass() -> None:
    evidence = json.loads(
        (ROOT / "docs/gate-3/corpus-invariants.json").read_text(encoding="utf-8")
    )

    assert evidence["passed"] is True
    assert evidence["scope"]["daily_feeds"] == 139
    assert evidence["scope"]["cases"] == 278
    assert evidence["total_invariant_violations"] == 0
    assert evidence["nondeterministic_cases"] == 0
    assert evidence["failed_invariant_cases"] == 0
    assert len(evidence["source_bindings"]) == 139
    assert len({item["raw_gdx_sha256"] for item in evidence["source_bindings"]}) == 139
    assert all(item["deterministic"] for item in evidence["cases"])
    assert all(item["invariants_passed"] for item in evidence["cases"])
