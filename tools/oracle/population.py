"""Acquire and hash the Authority-designated shortfall-transfer population."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PopulationManifest:
    source_release: str
    release_commit: str
    declared_affected_interval_count: int
    declared_trading_date_count: int
    dataset_url_template: str
    trading_dates: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> PopulationManifest:
        payload: dict[str, Any] = json.loads(path.read_text())
        manifest = cls(
            source_release=str(payload["source_release"]),
            release_commit=str(payload["release_commit"]),
            declared_affected_interval_count=int(
                payload["declared_affected_interval_count"]
            ),
            declared_trading_date_count=int(payload["declared_trading_date_count"]),
            dataset_url_template=str(payload["dataset_url_template"]),
            trading_dates=tuple(str(value) for value in payload["trading_dates"]),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if len(self.trading_dates) != self.declared_trading_date_count:
            raise ValueError("declared trading-date count does not match manifest")
        if len(set(self.trading_dates)) != len(self.trading_dates):
            raise ValueError("trading dates must be unique")
        if any(len(value) != 8 or not value.isdigit() for value in self.trading_dates):
            raise ValueError("trading dates must use YYYYMMDD")
        if self.declared_affected_interval_count <= 0:
            raise ValueError("declared affected-interval count must be positive")
        for field in ("{year}", "{yyyymmdd}"):
            if field not in self.dataset_url_template:
                raise ValueError(f"dataset URL template is missing {field}")

    def url(self, trading_date: str) -> str:
        if trading_date not in self.trading_dates:
            raise ValueError(f"date is not in the governed population: {trading_date}")
        return self.dataset_url_template.format(
            year=trading_date[:4], yyyymmdd=trading_date
        )


@dataclass(frozen=True)
class PopulationArtifact:
    trading_date: str
    path: str
    url: str
    size_bytes: int
    sha256: str


class PopulationAcquirer:
    """Concurrent, atomic downloader with a deterministic content inventory."""

    def __init__(
        self,
        download: Callable[[str, Path], None] | None = None,
    ) -> None:
        self.download = download or self._download

    def acquire(
        self,
        manifest: PopulationManifest,
        destination: Path,
        workers: int = 4,
    ) -> tuple[PopulationArtifact, ...]:
        if workers <= 0:
            raise ValueError("workers must be positive")
        destination.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            artifacts = tuple(
                executor.map(
                    lambda trading_date: self._acquire_one(
                        manifest, destination, trading_date
                    ),
                    manifest.trading_dates,
                )
            )
        return tuple(sorted(artifacts, key=lambda item: item.trading_date))

    def _acquire_one(
        self,
        manifest: PopulationManifest,
        destination: Path,
        trading_date: str,
    ) -> PopulationArtifact:
        year_directory = destination / trading_date[:4]
        year_directory.mkdir(parents=True, exist_ok=True)
        target = year_directory / f"Pricing_{trading_date}.gdx"
        url = manifest.url(trading_date)
        if not target.is_file():
            temporary = target.with_suffix(".gdx.part")
            self.download(url, temporary)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise ValueError(f"download produced no data: {url}")
            os.replace(temporary, target)
        return PopulationArtifact(
            trading_date=trading_date,
            path=target.relative_to(destination).as_posix(),
            url=url,
            size_bytes=target.stat().st_size,
            sha256=_sha256(target),
        )

    @staticmethod
    def _download(url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "pySPD-oracle/1"})
        with (
            urllib.request.urlopen(request, timeout=180) as response,
            destination.open("wb") as output,
        ):
            shutil.copyfileobj(response, output, length=1024 * 1024)


def write_inventory(
    manifest: PopulationManifest,
    artifacts: Sequence[PopulationArtifact],
    destination: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "source_release": manifest.source_release,
        "release_commit": manifest.release_commit,
        "declared_affected_interval_count": (
            manifest.declared_affected_interval_count
        ),
        "artifact_count": len(artifacts),
        "total_size_bytes": sum(artifact.size_bytes for artifact in artifacts),
        "artifacts": [asdict(artifact) for artifact in artifacts],
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args(argv)
    manifest = PopulationManifest.load(arguments.manifest)
    artifacts = PopulationAcquirer().acquire(
        manifest, arguments.destination, arguments.workers
    )
    write_inventory(manifest, artifacts, arguments.inventory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
