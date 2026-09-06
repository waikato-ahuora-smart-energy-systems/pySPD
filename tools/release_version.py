"""Keep release versions synchronized and advance PR candidates once per base."""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path

VERSION_FILES = ("pyproject.toml", "src/pyspd/__init__.py", "uv.lock")
RELEASE_FILES = (*VERSION_FILES, "README.md", "docs/getting-started.md")


def parse_version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError(f"expected a stable major.minor.patch version: {value!r}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def project_version(path: Path) -> str:
    value = str(tomllib.loads(path.read_text())["project"]["version"])
    parse_version(value)
    return value


def runtime_version(source: str) -> str:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError("missing literal pyspd.__version__")


def lock_version(source: str) -> str:
    packages = [
        package
        for package in tomllib.loads(source)["package"]
        if package["name"].lower() == "pyspd"
        and package.get("source") == {"editable": "."}
    ]
    if len(packages) != 1:
        raise ValueError("expected exactly one editable pyspd lock entry")
    return str(packages[0]["version"])


def requested_part(labels: list[str], title: str) -> str:
    normalized = {label.lower() for label in labels}
    for part in ("major", "minor", "patch"):
        if part in normalized:
            return part
    match = re.search(r"\[(major|minor|patch)\]", title, re.IGNORECASE)
    return match[1].lower() if match else "patch"


def next_version(current: str, base: str, part: str) -> str:
    current_parts = parse_version(current)
    base_parts = parse_version(base)
    if current_parts < base_parts:
        raise ValueError("candidate version is behind main; update the branch first")
    major, minor, patch = base_parts
    if part == "major":
        target = (major + 1, 0, 0)
    elif part == "minor":
        target = (major, minor + 1, 0)
    elif part == "patch":
        target = (major, minor, patch + 1)
    else:
        raise ValueError(f"unknown version part: {part}")
    # Repeated PR events do not increment again; larger labels still take effect.
    return ".".join(map(str, max(current_parts, target)))


def check_versions(root: Path, *, tag: str | None = None) -> str:
    version = project_version(root / "pyproject.toml")
    runtime = runtime_version((root / "src/pyspd/__init__.py").read_text())
    locked = lock_version((root / "uv.lock").read_text())
    if version != runtime or version != locked:
        raise ValueError(
            f"release versions differ: project={version}, runtime={runtime}, lock={locked}"
        )
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"release tag {tag!r} differs from package v{version}")
    return version


def replace_once(source: str, pattern: str, replacement: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return match[1] + replacement

    result, count = re.subn(pattern, replace, source)
    if count != 1:
        raise ValueError(f"expected exactly one version field matching {pattern!r}")
    return result


def bump_release(root: Path, base: str, part: str) -> str:
    current = check_versions(root)
    version = next_version(current, base, part)
    if current == version:
        return version
    sources = {name: (root / name).read_text() for name in RELEASE_FILES}
    old = re.escape(current)
    sources["pyproject.toml"] = replace_once(
        sources["pyproject.toml"],
        rf'(?m)(^\[project\]\n(?:(?!\[)[^\n]*\n)*?version = "){old}(?=")',
        version,
    )
    sources["src/pyspd/__init__.py"] = replace_once(
        sources["src/pyspd/__init__.py"],
        rf'(?m)(^__version__ = "){old}(?=")',
        version,
    )
    sources["uv.lock"] = replace_once(
        sources["uv.lock"],
        rf'(?m)(^name = "pyspd"\nversion = "){old}(?="\nsource = \{{ editable = "\." \}})',
        version,
    )
    for name in ("README.md", "docs/getting-started.md"):
        sources[name] = sources[name].replace(
            f"/blob/v{current}/", f"/blob/v{version}/"
        ).replace(f"pyspd-{current}-", f"pyspd-{version}-")
    # Validate every replacement before writing any file.
    for name, content in sources.items():
        (root / name).write_text(content)
    check_versions(root)
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "bump"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-pyproject", type=Path)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--tag")
    args = parser.parse_args()
    base = project_version(args.base_pyproject) if args.base_pyproject else None
    if args.command == "bump":
        if base is None or args.event is None:
            parser.error("bump requires --base-pyproject and --event")
        pr = json.loads(args.event.read_text())["pull_request"]
        part = requested_part([label["name"] for label in pr["labels"]], pr["title"])
        version = bump_release(args.root, base, part)
    else:
        version = check_versions(args.root, tag=args.tag)
        if base is not None and parse_version(version) <= parse_version(base):
            raise ValueError(f"release {version} must be newer than main's {base}")
    print(version)


if __name__ == "__main__":
    main()
