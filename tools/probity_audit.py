"""Fail-closed audit of committed Probity evidence coverage for every gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyspd.probity import TddEvidenceError, TddEvidenceValidator
from tools.evidence_paths import repository_evidence_path


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip()
        raise TddEvidenceError(f"git evidence query failed: {detail}") from error
    return completed.stdout.strip()


def _git_blob(root: Path, revision: str, path: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace").strip()
        raise TddEvidenceError(f"cannot read committed test blob: {detail}") from error
    return completed.stdout


def _committed_test_blob(
    root: Path, implementation: str, path: str, expected_sha256: str
) -> bytes:
    revisions = list(
        dict.fromkeys(
            [
                implementation,
                *_git(root, "rev-list", "HEAD", "--", path).splitlines(),
            ]
        )
    )
    for revision in revisions:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", implementation, revision],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if ancestor.returncode != 0:
            continue
        content = _git_blob(root, revision, path)
        if hashlib.sha256(content).hexdigest() == expected_sha256:
            return content
    raise TddEvidenceError(
        f"no committed test blob matches evidence for {path} after {implementation}"
    )


def changed_production_paths(
    root: Path, parent_commit: str, implementation_commit: str
) -> set[str]:
    output = _git(
        root,
        "diff",
        "--name-only",
        parent_commit,
        implementation_commit,
        "--",
        "src",
        "pyspd",
        "tools",
    )
    return {line for line in output.splitlines() if line}


def audit_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    validator = TddEvidenceValidator(
        root, root / "private/docs/gate-0/schemas/tdd-evidence.schema.json"
    )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    evidence_paths = sorted(root.glob("private/docs/gate-*/tdd/TDD-*.json"))
    if not evidence_paths:
        raise TddEvidenceError("no gate TDD evidence records found")
    for path in evidence_paths:
        environment_path = path.parent / "environment.json"
        if not environment_path.is_file():
            raise TddEvidenceError(
                f"missing gate environment manifest: {environment_path}"
            )
        environment_sha256 = hashlib.sha256(environment_path.read_bytes()).hexdigest()
        evidence = json.loads(path.read_text(encoding="utf-8"))
        implementation = evidence.get("implementation_commit")
        if not implementation:
            raise TddEvidenceError(f"unbound implementation commit: {path.name}")
        test_blobs = {
            item["path"]: _committed_test_blob(
                root, implementation, item["path"], item["sha256"]
            )
            for item in evidence["test_files"]
        }

        def committed_content(
            _revision: str,
            relative: str,
            blobs: dict[str, bytes] = test_blobs,
        ) -> bytes:
            return blobs[relative]

        # Preserve immutable records and hashes; relocate only filesystem lookups.
        relocated = dict(evidence)
        for phase in ("red", "green"):
            relocated[phase] = dict(evidence[phase])
            relocated[phase]["log_uri"] = str(
                repository_evidence_path(root, evidence[phase]["log_uri"])
                .relative_to(root)
            )
        validator.validate(
            relocated,
            changed_production_paths=evidence["production_paths"],
            expected_parent=evidence["parent_commit"],
            expected_implementation=implementation,
            expected_environment_sha256=environment_sha256,
            committed_test_content=committed_content,
        )
        grouped[(evidence["parent_commit"], implementation)].append(evidence)

    implementations: list[dict[str, Any]] = []
    for (parent, implementation), records in sorted(grouped.items()):
        direct_parent = _git(root, "rev-parse", f"{implementation}^")
        if direct_parent != parent:
            raise TddEvidenceError(
                f"{implementation} parent is {direct_parent}, evidence says {parent}"
            )
        changed = changed_production_paths(root, parent, implementation)
        covered = {
            path for evidence in records for path in evidence["production_paths"]
        }
        missing = sorted(changed - covered)
        extra = sorted(covered - changed)
        if missing or extra:
            raise TddEvidenceError(
                f"evidence coverage mismatch for {implementation}: "
                f"missing={missing}, extra={extra}"
            )
        implementations.append(
            {
                "parent_commit": parent,
                "implementation_commit": implementation,
                "production_paths": sorted(changed),
                "evidence_ids": sorted(item["evidence_id"] for item in records),
            }
        )
    return {
        "evidence_record_count": len(evidence_paths),
        "gate_count": len({path.parent.parent.name for path in evidence_paths}),
        "implementation_count": len(implementations),
        "implementations": implementations,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    result = audit_repository(_parser().parse_args(argv).root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
