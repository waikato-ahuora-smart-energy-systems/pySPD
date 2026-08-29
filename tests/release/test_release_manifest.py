from __future__ import annotations

import json

from pyspd.release import (
    DistributionStatus,
    LegalDecision,
    ReleaseManifest,
    ReleaseManifestBuilder,
)


def test_release_manifest_hashes_artifacts_and_holds_distribution(tmp_path) -> None:
    wheel = tmp_path / "pyspd-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "pyspd-0.1.0.tar.gz"
    sbom = tmp_path / "sbom.cdx.json"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    sbom.write_text('{"bomFormat":"CycloneDX"}\n')
    decisions = (
        LegalDecision("LIC-001", "pending"),
        LegalDecision("LIC-011", "approved"),
    )
    manifest = ReleaseManifestBuilder(tmp_path).build(
        version="0.1.0",
        formulation_ids=("vspd-v5.0.6-reserve",),
        artifacts=(wheel, sdist),
        sbom=sbom,
        evidence_sha256="5" * 64,
        legal_decisions=decisions,
    )
    assert manifest.distribution_status is DistributionStatus.HELD
    assert {item.name for item in manifest.artifacts} == {wheel.name, sdist.name}
    path = tmp_path / "release-manifest.json"
    manifest.write(path)
    assert ReleaseManifest.read(path) == manifest

    payload = json.loads(path.read_text())
    payload["version"] = "tampered"
    path.write_text(json.dumps(payload))
    try:
        ReleaseManifest.read(path)
    except ValueError as error:
        assert "hash" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("tampered release manifest was accepted")


def test_release_builder_fails_closed_for_missing_artifact(tmp_path) -> None:
    sbom = tmp_path / "sbom.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX"}\n')
    try:
        ReleaseManifestBuilder(tmp_path).build(
            version="0.1.0",
            formulation_ids=("vspd-v5.0.6-reserve",),
            artifacts=(tmp_path / "missing.whl",),
            sbom=sbom,
            evidence_sha256="5" * 64,
            legal_decisions=(),
        )
    except ValueError as error:
        assert "missing" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("missing release artifact was accepted")
