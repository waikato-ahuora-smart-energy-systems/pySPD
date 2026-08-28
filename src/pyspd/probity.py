"""Fail-closed validation for immutable Probity red/green evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


class TddEvidenceError(ValueError):
    """A red/green evidence record is absent, invalid, or incorrectly bound."""


def logical_test_patch_sha256(test_files: Sequence[Mapping[str, str]]) -> str:
    payload = json.dumps(
        sorted(
            ({"path": item["path"], "sha256": item["sha256"]} for item in test_files),
            key=lambda item: item["path"],
        ),
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


class TddEvidenceValidator:
    def __init__(self, root: Path, schema_path: Path) -> None:
        self.root = root.resolve()
        self.schema_path = schema_path.resolve()

    def validate(
        self,
        evidence: Mapping[str, Any],
        *,
        changed_production_paths: Sequence[str],
        expected_parent: str,
        expected_implementation: str,
        expected_environment_sha256: str,
    ) -> None:
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        try:
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).validate(dict(evidence))
        except ValidationError as error:
            location = ".".join(str(part) for part in error.absolute_path)
            raise TddEvidenceError(
                f"schema validation failed at {location or '<root>'}: {error.message}"
            ) from error

        if evidence["parent_commit"] != expected_parent:
            raise TddEvidenceError("parent commit does not match")
        if evidence.get("implementation_commit") != expected_implementation:
            raise TddEvidenceError("implementation commit does not match")
        if evidence["environment_manifest_sha256"] != expected_environment_sha256:
            raise TddEvidenceError("environment manifest does not match")
        if set(evidence["production_paths"]) != set(changed_production_paths):
            raise TddEvidenceError("evidence paths do not match changed production paths")
        if evidence["package_manager"] == "uv" and not evidence["command"].startswith(
            "uv run "
        ):
            raise TddEvidenceError("Python evidence command must begin with 'uv run'")

        test_files = evidence["test_files"]
        for item in test_files:
            path = self._within_root(item["path"])
            if self._file_sha256(path) != item["sha256"]:
                raise TddEvidenceError(f"test file hash mismatch: {item['path']}")
        if logical_test_patch_sha256(test_files) != evidence["test_patch_sha256"]:
            raise TddEvidenceError("test patch logical hash does not match")

        red_log = self._validated_log(evidence["red"], "red")
        self._validated_log(evidence["green"], "green")
        fingerprint = evidence["red"]["expected_failure_fingerprint"]
        infrastructure_markers = {
            "importerror",
            "modulenotfound",
            "no module named",
            "syntaxerror",
            "command not found",
            "infrastructure",
        }
        lowered = fingerprint.lower()
        if any(marker in lowered for marker in infrastructure_markers):
            raise TddEvidenceError("red fingerprint is not a behavioral failure")
        if fingerprint not in red_log:
            raise TddEvidenceError("behavioral failure fingerprint is absent from red log")

        exception = evidence.get("exception")
        if exception is not None:
            expiry = datetime.fromisoformat(exception["expires_at"])
            if expiry <= datetime.now(UTC):
                raise TddEvidenceError("TDD exception has expired")

    def _validated_log(self, run: Mapping[str, Any], label: str) -> str:
        uri = run.get("log_uri")
        if not uri:
            raise TddEvidenceError(f"{label} run has no retained log")
        path = self._within_root(uri)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != run["output_sha256"]:
            raise TddEvidenceError(f"{label} output hash mismatch")
        return content.decode("utf-8", errors="replace")

    def _within_root(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise TddEvidenceError(f"evidence path escapes repository: {relative}")
        return path

    @staticmethod
    def _file_sha256(path: Path) -> str:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise TddEvidenceError(f"cannot read evidence path {path}: {error}") from error
