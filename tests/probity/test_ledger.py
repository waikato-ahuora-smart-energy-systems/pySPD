from __future__ import annotations

from pathlib import Path

from tools.probity_audit import audit_repository

ROOT = Path(__file__).parents[2]


def test_all_gate_ledgers_cover_every_changed_production_path() -> None:
    result = audit_repository(ROOT)

    assert result["evidence_record_count"] >= 21
    assert result["implementation_count"] >= 3
