from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pyspd.probity import (
    TddEvidenceError,
    TddEvidenceValidator,
    logical_test_patch_sha256,
)

PARENT = "a" * 40
IMPLEMENTATION = "b" * 40
ENVIRONMENT = "c" * 64


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def valid_evidence(root: Path) -> dict[str, Any]:
    test = root / "tests" / "test_rule.py"
    test.parent.mkdir(parents=True)
    test.write_text("def test_rule(): assert True\n")
    test_files = [{"path": "tests/test_rule.py", "sha256": sha256(test.read_bytes())}]
    return {
        "schema_version": "1.0.0",
        "evidence_id": "TDD-G2-RULE",
        "requirement_ids": ["REQ-G2-TDD"],
        "production_paths": ["src/pyspd/rule.py"],
        "parent_commit": PARENT,
        "implementation_commit": IMPLEMENTATION,
        "test_patch_sha256": logical_test_patch_sha256(test_files),
        "test_files": test_files,
        "command": "uv run pytest tests/test_rule.py",
        "package_manager": "uv",
        "environment_manifest_sha256": ENVIRONMENT,
        "red": {
            "timestamp": "2026-08-29T00:00:00Z",
            "exit_code": 1,
            "output_sha256": "d" * 64,
            "duration_seconds": 0.1,
            "expected_failure_fingerprint": "REQ-G2-TDD: missing behavior",
            "log_uri": "evidence/red.log",
        },
        "green": {
            "timestamp": "2026-08-29T00:01:00Z",
            "exit_code": 0,
            "output_sha256": "e" * 64,
            "duration_seconds": 0.1,
            "log_uri": "evidence/green.log",
        },
        "author": {"name": "Codex", "role": "implementation agent"},
        "reviewer": {"name": "Codex", "role": "project-directed validator"},
        "exception": None,
    }


def validator(root: Path) -> TddEvidenceValidator:
    schema = Path(__file__).parents[2] / "private/docs/gate-0/schemas/tdd-evidence.schema.json"
    return TddEvidenceValidator(root, schema)


def write_logs(root: Path, evidence: dict[str, Any]) -> None:
    evidence_dir = root / "evidence"
    evidence_dir.mkdir()
    red = b"FAILED REQ-G2-TDD: missing behavior\n"
    green = b"1 passed\n"
    (evidence_dir / "red.log").write_bytes(red)
    (evidence_dir / "green.log").write_bytes(green)
    evidence["red"]["output_sha256"] = sha256(red)
    evidence["green"]["output_sha256"] = sha256(green)


def validate(root: Path, evidence: dict[str, Any]) -> None:
    validator(root).validate(
        evidence,
        changed_production_paths=["src/pyspd/rule.py"],
        expected_parent=PARENT,
        expected_implementation=IMPLEMENTATION,
        expected_environment_sha256=ENVIRONMENT,
    )


def test_valid_red_green_record_is_fully_bound(tmp_path: Path) -> None:
    evidence = valid_evidence(tmp_path)
    write_logs(tmp_path, evidence)

    validate(tmp_path, evidence)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item.update(parent_commit="f" * 40), "parent"),
        (lambda item: item["test_files"][0].update(sha256="f" * 64), "test file"),
        (
            lambda item: item["red"].update(
                expected_failure_fingerprint="ImportError infrastructure"
            ),
            "behavioral",
        ),
        (lambda item: item.update(production_paths=["src/pyspd/other.py"]), "changed"),
    ],
)
def test_mismatched_evidence_is_rejected(
    tmp_path: Path, mutation: Any, message: str
) -> None:
    evidence = valid_evidence(tmp_path)
    write_logs(tmp_path, evidence)
    mutation(evidence)

    with pytest.raises(TddEvidenceError, match=message):
        validate(tmp_path, evidence)


def test_expired_exception_is_rejected(tmp_path: Path) -> None:
    evidence = valid_evidence(tmp_path)
    write_logs(tmp_path, evidence)
    evidence["exception"] = {
        "reason": "Mechanical generated-file update with no behavior",
        "approver": {"name": "Owner", "role": "project owner"},
        "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "follow_up_test": "REQ-G2-TDD",
    }

    with pytest.raises(TddEvidenceError, match="expired"):
        validate(tmp_path, evidence)
