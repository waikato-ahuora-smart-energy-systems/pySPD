"""Inspect release archives and exercise a wheel in an isolated environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from tools.release_version import lock_version, runtime_version


def inspect_artifacts(
    artifacts: Path, expected_version: str | None = None
) -> dict[str, object]:
    wheels = list(artifacts.glob("*.whl"))
    sources = list(artifacts.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("qualification requires exactly one wheel and one sdist")
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = archive.namelist()
        if any(not name.startswith(("pyspd/", "pyspd-")) for name in wheel_names):
            raise ValueError("unexpected top-level wheel content")
        lock = archive.read("pyspd/_build/uv.lock")
        metadata = BytesParser().parsebytes(
            archive.read(
                next(
                    name for name in wheel_names if name.endswith(".dist-info/METADATA")
                )
            )
        )
        version = metadata["Version"]
        if expected_version is not None and version != expected_version:
            raise ValueError("wheel version differs from the release tag")
        if wheels[0].name != f"pyspd-{version}-py3-none-any.whl":
            raise ValueError("wheel filename differs from its metadata version")
        if runtime_version(archive.read("pyspd/__init__.py").decode()) != version:
            raise ValueError("wheel runtime version differs from its metadata")
        if lock_version(lock.decode()) != version:
            raise ValueError("wheel lock version differs from its metadata")
        requirements = metadata.get_all("Requires-Dist", [])
        if metadata.get("License-Expression") != "Apache-2.0":
            raise ValueError("wheel does not declare Apache-2.0")
        if "LICENSE" not in metadata.get_all("License-File", []):
            raise ValueError("wheel metadata does not identify LICENSE")
        license_name = next(
            name for name in wheel_names if name.endswith(".dist-info/licenses/LICENSE")
        )
        license_text = archive.read(license_name)
        if not license_text.strip():
            raise ValueError("wheel licence is empty")
        for dependency, solver in (("pyscipopt", "SCIP"), ("highspy", "HiGHS")):
            if not any(
                item.lower().startswith(dependency) and ";" not in item
                for item in requirements
            ):
                raise ValueError(f"wheel does not install {solver} by default")
        if not {"gdx", "clp", "cbc"} <= set(metadata.get_all("Provides-Extra", [])):
            raise ValueError("wheel is missing supported installation extras")
    with tarfile.open(sources[0]) as source_archive:
        if sources[0].name != f"pyspd-{version}.tar.gz":
            raise ValueError("sdist filename differs from the wheel version")
        prefix = f"pyspd-{version}/"

        def read_source(name: str) -> bytes:
            stream = source_archive.extractfile(prefix + name)
            if stream is None:
                raise ValueError(f"missing sdist file: {name}")
            return stream.read()

        source_metadata = BytesParser().parsebytes(read_source("PKG-INFO"))
        source_project = tomllib.loads(read_source("pyproject.toml").decode())["project"]
        if (
            source_metadata["Version"] != version
            or source_project["version"] != version
            or runtime_version(read_source("src/pyspd/__init__.py").decode()) != version
        ):
            raise ValueError("sdist versions differ from the wheel version")
        source_names = source_archive.getnames()
        allowed = {
            "src",
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "CHANGELOG.md",
            "LICENSE",
            "PKG-INFO",
            ".gitignore",
        }
        for name in source_names:
            parts = PurePosixPath(name).parts
            if len(parts) > 1 and parts[1] not in allowed:
                raise ValueError(f"unexpected sdist content: {name}")
        member = next(
            item for item in source_archive.getmembers() if item.name.endswith("/uv.lock")
        )
        stream = source_archive.extractfile(member)
        if stream is None or stream.read() != lock:
            raise ValueError("wheel and sdist build locks differ")
        license_member = next(
            item for item in source_archive.getmembers() if item.name.endswith("/LICENSE")
        )
        license_stream = source_archive.extractfile(license_member)
        if license_stream is None or license_stream.read() != license_text:
            raise ValueError("wheel and sdist licences differ")
    for name in wheel_names + source_names:
        if any(
            part in {"private", "tests", "docs", "tools", "evidence"}
            for part in PurePosixPath(name).parts
        ):
            raise ValueError(
                f"internal or qualification material in distribution: {name}"
            )
        if name.endswith((".gdx", ".g00", ".jsonl")):
            raise ValueError(f"external data in distribution: {name}")
    return {
        "version": version,
        "artifacts": [
            {
                "name": p.name,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "size": p.stat().st_size,
            }
            for p in (wheels[0], sources[0])
        ],
        "wheel_file_count": len(wheel_names),
        "sdist_file_count": len(source_names),
        "build_lock_sha256": hashlib.sha256(lock).hexdigest(),
        "requirements": requirements,
        "license_expression": metadata["License-Expression"],
        "license_sha256": hashlib.sha256(license_text).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gams-system-directory", type=Path)
    parser.add_argument("--expected-version")
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    inspection = inspect_artifacts(artifacts, args.expected_version)
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv must be on PATH")
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    with tempfile.TemporaryDirectory(prefix="pyspd-wheel-") as directory:
        work = Path(directory)
        with (output / "installation.log").open("w") as log:

            def run(command: list[str]) -> None:
                subprocess.run(
                    command,
                    cwd=work,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )

            run([uv, "venv", "--python", sys.executable, str(work / "venv")])
            python = work / "venv/bin/python"
            wheel = str(next(artifacts.glob("*.whl")))
            run([uv, "pip", "install", "--python", str(python), wheel])
            # Copy only synthetic fixture helpers; production imports must come
            # from the installed wheel, which the smoke program asserts.
            for family in ("network", "hvdc", "reserve"):
                target = work / "tests" / family
                target.mkdir(parents=True, exist_ok=True)
                (target / "__init__.py").touch()
                shutil.copyfile(
                    root / "tests" / family / "conftest.py", target / "conftest.py"
                )
            (work / "tests/__init__.py").touch()
            shutil.copyfile(
                root / "tests/release/installed_smoke.py", work / "smoke.py"
            )
            run([str(work / "venv/bin/pyspd"), "formulations", "--json"])
            run([str(python), "-I", "smoke.py"])
            core = json.loads((work / "smoke-result.json").read_text())
            if core["version"] != inspection["version"]:
                raise ValueError("installed runtime version differs from the artifacts")
            extra = None
            if args.gams_system_directory:
                run([uv, "pip", "install", "--python", str(python), wheel + "[gdx]"])
                run(
                    [
                        str(python),
                        "-I",
                        "smoke.py",
                        str(args.gams_system_directory.resolve()),
                    ]
                )
                extra = json.loads((work / "smoke-result.json").read_text())
            result = {**inspection, "core_install": core, "gdx_install": extra}
            (output / "qualification.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )
            print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
