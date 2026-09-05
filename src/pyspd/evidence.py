"""Hash-bound acquisition of large, optional validation evidence."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any


class EvidenceError(ValueError):
    """Evidence metadata, content, or extraction violates the trust boundary."""


def _json_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    """One immutable downloadable evidence archive."""

    artifact_id: str
    version: str
    url: str
    sha256: str
    size_bytes: int
    description: str
    file_count: int = 0
    uncompressed_size_bytes: int = 0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", self.artifact_id):
            raise EvidenceError("artifact id must be lowercase and filesystem-safe")
        if not self.version.strip():
            raise EvidenceError("artifact version must not be empty")
        parsed = urllib.parse.urlparse(self.url)
        if parsed.scheme not in {"https", "file"}:
            raise EvidenceError("evidence URL must use https or file")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise EvidenceError("artifact SHA-256 must be lowercase hexadecimal")
        if isinstance(self.size_bytes, bool) or self.size_bytes <= 0:
            raise EvidenceError("artifact size must be a positive integer")
        if not self.description.strip():
            raise EvidenceError("artifact description must not be empty")
        if self.file_count < 0 or self.uncompressed_size_bytes < 0:
            raise EvidenceError("artifact content counts must be nonnegative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "version": self.version,
            "url": self.url,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "description": self.description,
            "file_count": self.file_count,
            "uncompressed_size_bytes": self.uncompressed_size_bytes,
        }


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    """Canonical index of independently stored validation evidence."""

    schema_version: int
    artifacts: tuple[EvidenceArtifact, ...]
    logical_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise EvidenceError("unsupported evidence manifest schema version")
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        identifiers = [artifact.artifact_id for artifact in self.artifacts]
        if len(identifiers) != len(set(identifiers)):
            raise EvidenceError("duplicate artifact id in evidence manifest")
        object.__setattr__(self, "logical_sha256", _json_sha256(self.to_dict()))

    def to_dict(self, *, include_logical_sha256: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "artifacts": [
                artifact.to_dict()
                for artifact in sorted(self.artifacts, key=lambda item: item.artifact_id)
            ],
        }
        if include_logical_sha256:
            payload["logical_sha256"] = self.logical_sha256
        return payload

    @classmethod
    def from_json(cls, path: Path) -> EvidenceManifest:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifacts = tuple(
                EvidenceArtifact(
                    artifact_id=str(item["artifact_id"]),
                    version=str(item["version"]),
                    url=str(item["url"]),
                    sha256=str(item["sha256"]),
                    size_bytes=int(item["size_bytes"]),
                    description=str(item["description"]),
                    file_count=int(item.get("file_count", 0)),
                    uncompressed_size_bytes=int(
                        item.get("uncompressed_size_bytes", 0)
                    ),
                )
                for item in raw["artifacts"]
            )
            manifest = cls(schema_version=int(raw["schema_version"]), artifacts=artifacts)
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise EvidenceError(f"invalid evidence manifest: {path}") from error
        declared = raw.get("logical_sha256")
        if declared is not None and declared != manifest.logical_sha256:
            raise EvidenceError("evidence manifest logical SHA-256 mismatch")
        return manifest

    def artifact(self, artifact_id: str) -> EvidenceArtifact:
        for artifact in self.artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        raise EvidenceError(f"unknown evidence artifact: {artifact_id}")


@dataclass(frozen=True, slots=True)
class EvidenceFetchResult:
    artifact: EvidenceArtifact
    archive_path: Path
    destination: Path
    extracted_files: tuple[Path, ...]
    downloaded: bool
    verified: bool = True


@dataclass(frozen=True, slots=True)
class EvidenceArchiveResult:
    path: Path
    sha256: str
    size_bytes: int
    uncompressed_size_bytes: int
    file_count: int


class EvidenceArchiveBuilder:
    """Create byte-reproducible gzip/tar archives from repository paths."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def build(
        self, source_paths: tuple[Path, ...], output_path: Path
    ) -> EvidenceArchiveResult:
        files = self._files(source_paths)
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output_path.name}-", suffix=".part", dir=output_path.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with (
                temporary.open("wb") as raw,
                gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped,
                tarfile.open(
                    fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT
                ) as archive,
            ):
                for relative, source in files:
                    info = tarfile.TarInfo(relative.as_posix())
                    info.size = source.stat().st_size
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    with source.open("rb") as handle:
                        archive.addfile(info, handle)
            temporary.replace(output_path)
        finally:
            temporary.unlink(missing_ok=True)
        return EvidenceArchiveResult(
            path=output_path,
            sha256=_file_sha256(output_path),
            size_bytes=output_path.stat().st_size,
            uncompressed_size_bytes=sum(source.stat().st_size for _, source in files),
            file_count=len(files),
        )

    def _files(self, source_paths: tuple[Path, ...]) -> tuple[tuple[Path, Path], ...]:
        selected: dict[str, tuple[Path, Path]] = {}
        for source_path in source_paths:
            if source_path.is_absolute() or ".." in source_path.parts:
                raise EvidenceError(f"archive source must be relative: {source_path}")
            source = (self.root / source_path).resolve()
            if not source.is_relative_to(self.root) or not source.exists():
                raise EvidenceError(f"archive source does not exist: {source_path}")
            candidates = (source,) if source.is_file() else source.rglob("*")
            for candidate in candidates:
                if candidate.is_symlink():
                    raise EvidenceError(f"archive source is a symlink: {candidate}")
                if not candidate.is_file():
                    continue
                relative = candidate.relative_to(self.root)
                selected[relative.as_posix()] = (relative, candidate)
        if not selected:
            raise EvidenceError("evidence archive must contain at least one file")
        return tuple(selected[name] for name in sorted(selected))


class EvidenceStore:
    """Download, verify, and safely rehydrate immutable evidence archives."""

    def __init__(self, cache_directory: Path, *, auth_token: str | None = None) -> None:
        self.cache_directory = cache_directory.expanduser().resolve()
        self.auth_token = auth_token

    def archive_path(self, artifact: EvidenceArtifact) -> Path:
        suffix = ".tar.gz" if artifact.url.endswith((".tar.gz", ".tgz")) else ".archive"
        name = (
            f"{artifact.artifact_id}-{artifact.version}-"
            f"{artifact.sha256[:12]}{suffix}"
        )
        return self.cache_directory / name

    def verify(self, artifact: EvidenceArtifact) -> Path:
        path = self.archive_path(artifact)
        if not path.is_file():
            raise EvidenceError(f"evidence archive is not cached: {artifact.artifact_id}")
        digest = _file_sha256(path)
        if digest != artifact.sha256:
            raise EvidenceError(
                f"evidence SHA-256 mismatch for {artifact.artifact_id}: {digest}"
            )
        size = path.stat().st_size
        if size != artifact.size_bytes:
            raise EvidenceError(
                f"evidence size mismatch for {artifact.artifact_id}: {size}"
            )
        return path

    def fetch(
        self, artifact: EvidenceArtifact, *, destination: Path
    ) -> EvidenceFetchResult:
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        archive_path = self.archive_path(artifact)
        downloaded = not archive_path.exists()
        if downloaded:
            self._download(artifact, archive_path)
        self.verify(artifact)
        destination = destination.expanduser().resolve()
        extracted = self._extract(archive_path, destination)
        return EvidenceFetchResult(
            artifact=artifact,
            archive_path=archive_path,
            destination=destination,
            extracted_files=extracted,
            downloaded=downloaded,
        )

    def _download(self, artifact: EvidenceArtifact, target: Path) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{artifact.artifact_id}-", suffix=".part", dir=self.cache_directory
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            download_url = self._download_url(artifact.url)
            request = urllib.request.Request(
                download_url,
                headers=(
                    {
                        "Accept": "application/octet-stream",
                        "Authorization": f"Bearer {self.auth_token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    }
                    if self.auth_token is not None
                    else {}
                ),
            )
            with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            digest = _file_sha256(temporary)
            if digest != artifact.sha256:
                raise EvidenceError(
                    f"evidence SHA-256 mismatch for {artifact.artifact_id}: {digest}"
                )
            size = temporary.stat().st_size
            if size != artifact.size_bytes:
                raise EvidenceError(
                    f"evidence size mismatch for {artifact.artifact_id}: {size}"
                )
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def _download_url(self, url: str) -> str:
        if self.auth_token is None:
            return url
        parsed = urllib.parse.urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if (
            parsed.hostname != "github.com"
            or len(parts) < 6
            or parts[2:4] != ["releases", "download"]
        ):
            return url
        owner, repository, _, _, tag, *asset_parts = parts
        asset_name = "/".join(asset_parts)
        release_url = (
            f"https://api.github.com/repos/{owner}/{repository}/releases/tags/"
            f"{urllib.parse.quote(tag, safe='')}"
        )
        request = urllib.request.Request(
            release_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.auth_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request) as response:
            release = json.load(response)
        for asset in release.get("assets", ()):
            if asset.get("name") == asset_name:
                return str(asset["url"])
        raise EvidenceError(f"release asset was not found: {asset_name}")

    def _extract(self, archive_path: Path, destination: Path) -> tuple[Path, ...]:
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="pyspd-evidence-", dir=self.cache_directory
        ) as temporary_name:
            temporary = Path(temporary_name)
            files: list[Path] = []
            with tarfile.open(archive_path, "r:gz") as archive:
                members = archive.getmembers()
                for member in members:
                    relative = _safe_member_path(member)
                    if member.isdir():
                        continue
                    source = archive.extractfile(member)
                    if source is None:
                        raise EvidenceError(f"archive member has no content: {member.name}")
                    staged = temporary / relative
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    with staged.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    files.append(relative)
            for relative in files:
                staged = temporary / relative
                target = destination / relative
                if target.exists() and (
                    not target.is_file() or _file_sha256(target) != _file_sha256(staged)
                ):
                    raise EvidenceError(f"destination content differs: {relative}")
            for relative in files:
                staged = temporary / relative
                target = destination / relative
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                staged.replace(target)
        return tuple(sorted(files, key=lambda item: item.as_posix()))


def _safe_member_path(member: tarfile.TarInfo) -> Path:
    pure = PurePosixPath(member.name)
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or not pure.parts
        or member.issym()
        or member.islnk()
        or not (member.isfile() or member.isdir())
    ):
        raise EvidenceError(f"unsafe archive member: {member.name}")
    return Path(*pure.parts)


def default_evidence_cache() -> Path:
    configured = os.environ.get("PYSPD_EVIDENCE_CACHE")
    if configured:
        return Path(configured)
    return Path.home() / ".cache" / "pyspd" / "evidence"


def github_credential() -> str:
    """Read the configured GitHub credential without printing or persisting it."""

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
        raise EvidenceError("no GitHub credential is available") from error


__all__ = [
    "EvidenceArchiveBuilder",
    "EvidenceArchiveResult",
    "EvidenceArtifact",
    "EvidenceError",
    "EvidenceFetchResult",
    "EvidenceManifest",
    "EvidenceStore",
    "default_evidence_cache",
    "github_credential",
]
