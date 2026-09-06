"""Execute standalone notebook examples in separate temporary working folders.

Run with the notebook requirements installed, including the published PySPD
version. No production source or fixture helpers are copied into the workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import tempfile
import time
from pathlib import Path


def main() -> None:
    import nbformat
    from nbclient import NotebookClient

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebooks", type=Path, default=Path("examples/notebooks"))
    parser.add_argument("--output", type=Path, default=Path("dist/notebook-validation"))
    parser.add_argument("--write-executed", action="store_true")
    parser.add_argument("--only", help="Execute only filenames matching this glob")
    args = parser.parse_args()
    sources = sorted(args.notebooks.glob(args.only or "*.ipynb"))
    if not sources:
        raise ValueError("no notebooks found")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in {"PYTHONPATH", "PYTHONHOME"} and not name.startswith("PYSPD_")
    }
    for source in sources:
        notebook = nbformat.read(source, as_version=4)
        nbformat.validate(notebook)
        for cell in notebook.cells:
            if cell.cell_type == "code":
                cell.outputs = []
                cell.execution_count = None
        # Assert the kernel actually uses an installed package, not the checkout.
        probe = nbformat.v4.new_code_cell(
            "import pathlib, sys, pyspd\n"
            "assert pathlib.Path(pyspd.__file__).resolve().is_relative_to("
            "pathlib.Path(sys.prefix).resolve()), pyspd.__file__"
        )
        notebook.cells.insert(0, probe)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="pyspd-notebook-") as directory:
            client = NotebookClient(
                notebook,
                timeout=180,
                kernel_name="python3",
                resources={"metadata": {"path": directory}},
                record_timing=False,
                allow_errors=False,
            )
            client.execute(env=env)
        notebook.cells.pop(0)
        for cell in notebook.cells:
            if cell.cell_type == "code" and cell.execution_count is not None:
                cell.execution_count -= 1
        nbformat.validate(notebook)
        target = args.output / source.name
        nbformat.write(notebook, target)
        if args.write_executed:
            nbformat.write(notebook, source)
        code_cells = [c for c in notebook.cells if c.cell_type == "code"]
        result = {
            "notebook": source.name,
            "code_cells": len(code_cells),
            "plots": sum(
                "image/png" in output.get("data", {})
                for cell in code_cells
                for output in cell.outputs
            ),
            "external_input_required": notebook.metadata.pyspd_example[
                "external_input_required"
            ],
            "scope": (
                "unconfigured path only; external GDX solve not run"
                if notebook.metadata.pyspd_example["external_input_required"]
                else "all cells executed with synthetic input"
            ),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
        results.append(result)
        print(json.dumps(result), flush=True)
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "pyspd",
                "pyscipopt",
                "highspy",
                "nbclient",
                "nbformat",
                "jupyterlab",
                "matplotlib",
                "pandas",
            )
        },
        "results": results,
    }
    (args.output / "execution-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
