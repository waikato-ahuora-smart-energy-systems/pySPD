from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.oracle.population import (
    PopulationAcquirer,
    PopulationManifest,
    write_inventory,
)


def _manifest(path: Path) -> PopulationManifest:
    path.write_text(
        json.dumps(
            {
                "source_release": "https://example.invalid/release",
                "release_commit": "abc123",
                "declared_affected_interval_count": 2,
                "declared_trading_date_count": 2,
                "dataset_url_template": (
                    "https://example.invalid/{year}/Pricing_{yyyymmdd}.gdx"
                ),
                "trading_dates": ["20240101", "20240102"],
            }
        )
    )
    return PopulationManifest.load(path)


def test_population_acquisition_is_atomic_hashed_and_deterministic(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "manifest.json")

    def download(url: str, destination: Path) -> None:
        destination.write_bytes(url.encode())

    artifacts = PopulationAcquirer(download).acquire(
        manifest, tmp_path / "inputs", workers=2
    )
    inventory = tmp_path / "inventory.json"
    write_inventory(manifest, artifacts, inventory)
    payload = json.loads(inventory.read_text())

    assert [artifact.trading_date for artifact in artifacts] == [
        "20240101",
        "20240102",
    ]
    assert all(len(artifact.sha256) == 64 for artifact in artifacts)
    assert payload["artifact_count"] == 2
    assert not list((tmp_path / "inputs").rglob("*.part"))


def test_population_manifest_rejects_count_and_date_errors(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "source_release": "x",
                "release_commit": "x",
                "declared_affected_interval_count": 1,
                "declared_trading_date_count": 2,
                "dataset_url_template": "x/{year}/{yyyymmdd}",
                "trading_dates": ["bad"],
            }
        )
    )

    with pytest.raises(ValueError, match="count"):
        PopulationManifest.load(path)


def test_governed_manifest_has_exact_authority_population() -> None:
    path = (
        Path(__file__).parents[2]
        / "private/docs"
        / "gate-1"
        / "shortfall-transfer-population.json"
    )
    manifest = PopulationManifest.load(path)

    assert manifest.declared_trading_date_count == len(manifest.trading_dates) == 139
    assert manifest.declared_affected_interval_count == 546
    assert manifest.trading_dates[0] == "20221106"
    assert manifest.trading_dates[-1] == "20250125"
