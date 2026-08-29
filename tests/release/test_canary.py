from __future__ import annotations

import json

from pyspd.canary import (
    CanaryBaseline,
    CanaryStatus,
    ContinuousValidationCanary,
    QuarantineStore,
)
from pyspd.reporting import ReportManifest


def baseline() -> CanaryBaseline:
    return CanaryBaseline(
        formulation_id="vspd-v5.0.6-reserve",
        report_manifest_sha256="1" * 64,
        report_files={"published_price.csv": "2" * 64},
        source_sha256="3" * 64,
    )


def candidate(*, manifest: str = "1" * 64, report: str = "2" * 64) -> ReportManifest:
    return ReportManifest(
        "vspd-v5.0.6-reserve",
        "4" * 64,
        {"published_price.csv": report},
        manifest,
    )


def test_exact_candidate_passes_without_mutating_baseline() -> None:
    expected = baseline()
    before = expected.logical_sha256
    result = ContinuousValidationCanary().evaluate(expected, candidate())
    assert result.status is CanaryStatus.PASS
    assert not result.discrepancies
    assert expected.logical_sha256 == before


def test_mismatch_is_quarantined_and_cannot_rewrite_baseline(tmp_path) -> None:
    expected = baseline()
    result = ContinuousValidationCanary().evaluate(
        expected, candidate(report="9" * 64)
    )
    assert result.status is CanaryStatus.QUARANTINED
    assert result.discrepancies == ("published_price.csv hash mismatch",)
    path = QuarantineStore(tmp_path).record(result)
    payload = json.loads(path.read_text())
    assert payload["baseline_sha256"] == expected.logical_sha256
    assert not (tmp_path / "baseline.json").exists()
    try:
        QuarantineStore(tmp_path).record(result)
    except FileExistsError:
        pass
    else:  # pragma: no cover - assertion guard
        raise AssertionError("quarantine evidence was overwritten")


def test_wrong_formulation_is_unsupported_not_compared() -> None:
    wrong = ReportManifest("vspd-v16.0", "4" * 64, {}, "5" * 64)
    result = ContinuousValidationCanary().evaluate(baseline(), wrong)
    assert result.status is CanaryStatus.UNSUPPORTED
    assert "formulation" in result.discrepancies[0]
