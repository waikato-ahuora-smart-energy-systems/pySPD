"""Publish prebuilt evidence archives as a guarded GitHub release."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class PublicationError(RuntimeError):
    """The guarded release publication could not complete."""


class GitHubReleasePublisher:
    """Create or resume a draft release without replacing existing assets."""

    def __init__(self, repository: str, token: str) -> None:
        self.repository = repository
        self.token = token
        self.api = f"https://api.github.com/repos/{repository}"

    def publish(
        self,
        *,
        tag: str,
        target: str,
        title: str,
        body: str,
        manifest: Path,
        archives: tuple[Path, ...],
    ) -> dict[str, Any]:
        release = self._release(tag)
        if release is None:
            release = self._json_request(
                f"{self.api}/releases",
                method="POST",
                payload={
                    "tag_name": tag,
                    "target_commitish": target,
                    "name": title,
                    "body": body,
                    "draft": True,
                    "prerelease": False,
                },
            )
        if not release.get("draft"):
            raise PublicationError("evidence release already exists and is not a draft")
        paths = (manifest, *archives)
        existing = {asset["name"]: asset for asset in release.get("assets", ())}
        upload_url = str(release["upload_url"]).split("{", 1)[0]
        for path in paths:
            asset = existing.get(path.name)
            if asset is not None:
                if int(asset["size"]) != path.stat().st_size:
                    raise PublicationError(
                        f"existing release asset has a different size: {path.name}"
                    )
                continue
            query = urllib.parse.urlencode({"name": path.name})
            self._binary_request(
                f"{upload_url}?{query}",
                path,
                content_type=(
                    "application/json"
                    if path.suffix == ".json"
                    else "application/gzip"
                ),
            )
        release = self._json_request(
            f"{self.api}/releases/{release['id']}",
            method="PATCH",
            payload={"draft": False},
        )
        return release

    def upload_existing(self, *, tag: str, path: Path) -> dict[str, Any]:
        """Add one immutable asset to an existing release."""

        release = self._release(tag)
        if release is None:
            raise PublicationError(f"release does not exist: {tag}")
        existing = {asset["name"]: asset for asset in release.get("assets", ())}
        asset = existing.get(path.name)
        if asset is not None:
            if int(asset["size"]) != path.stat().st_size:
                raise PublicationError(
                    f"existing release asset has a different size: {path.name}"
                )
            return asset
        upload_url = str(release["upload_url"]).split("{", 1)[0]
        query = urllib.parse.urlencode({"name": path.name})
        return self._binary_request(
            f"{upload_url}?{query}", path, content_type="application/octet-stream"
        )

    def _release(self, tag: str) -> dict[str, Any] | None:
        try:
            return self._json_request(f"{self.api}/releases/tags/{tag}")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def _headers(self, content_type: str = "application/vnd.github+json") -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": content_type,
            "User-Agent": "pyspd-evidence-publisher",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _json_request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            url, method=method, data=data, headers=self._headers()
        )
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def _binary_request(
        self, url: str, path: Path, *, content_type: str
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            method="POST",
            data=path.read_bytes(),
            headers=self._headers(content_type),
        )
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
        if int(payload.get("size", -1)) != path.stat().st_size:
            raise PublicationError(f"uploaded asset size mismatch: {path.name}")
        return payload


def _credential() -> str:
    configured = os.environ.get("GITHUB_TOKEN")
    if configured:
        return configured
    result = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
        check=True,
    )
    fields = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    try:
        return fields["password"]
    except KeyError as error:
        raise PublicationError("no GitHub credential is available") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--directory", type=Path)
    source.add_argument("--asset", type=Path)
    parser.add_argument(
        "--repository",
        default="waikato-ahuora-smart-energy-systems/pySPD",
    )
    parser.add_argument("--tag", default="evidence-v1")
    parser.add_argument("--target", default="main")
    arguments = parser.parse_args()
    publisher = GitHubReleasePublisher(arguments.repository, _credential())
    if arguments.asset is not None:
        asset = publisher.upload_existing(
            tag=arguments.tag, path=arguments.asset.resolve()
        )
        print(
            json.dumps(
                {
                    "asset": asset["name"],
                    "size_bytes": asset["size"],
                    "state": asset["state"],
                },
                sort_keys=True,
            )
        )
        return
    assert arguments.directory is not None
    directory = arguments.directory.resolve()
    manifest = directory / "manifest-v1.json"
    archives = tuple(sorted(directory.glob("*.tar.gz")))
    if not manifest.is_file() or len(archives) != 4:
        raise PublicationError("expected one manifest and four evidence archives")
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    release = publisher.publish(
        tag=arguments.tag,
        target=arguments.target,
        title="PySPD validation evidence v1",
        body=(
            "Hash-bound GDX, CPLEX, and detailed Gate 12 validation evidence.\n\n"
            f"Manifest logical SHA-256: `{manifest_payload['logical_sha256']}`"
        ),
        manifest=manifest,
        archives=archives,
    )
    print(
        json.dumps(
            {
                "asset_count": len(release.get("assets", ())),
                "html_url": release["html_url"],
                "published": not release["draft"],
                "tag": release["tag_name"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
