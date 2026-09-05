# Getting started

## Prerequisites

You need:

- Python 3.13;
- [`uv`](https://docs.astral.sh/uv/) for environments and package execution;
- a GAMS installation capable of reading GDX files; and
- enough memory for the selected number of independent solver workers.

The default path uses PySCIPOpt for the MIP and `highspy` for the fixed RMIP.
GAMS is used at the data boundary; the normal PySPD solve does not execute the
GAMS model.

## Install

From the repository root:

```shell
uv sync --frozen
uv run pyspd formulations --json
```

Install optional groups only when needed:

```shell
uv sync --frozen --group gdx       # GDX/GAMSPy data tooling
uv sync --frozen --group oracle    # GAMS-oracle tooling
uv sync --frozen --group docs      # documentation site
```

`uv.lock` is authoritative. Keep `--frozen` on qualification and comparison
runs so dependency resolution cannot silently change.

## Locate the GAMS system directory

Common locations are:

=== "macOS framework install"

    ```text
    /Library/Frameworks/GAMS.framework/Resources
    ```

=== "Linux"

    ```text
    /opt/gams/gams<version>_linux_x64_64_sfx
    ```

Use the directory that contains the GAMS executable and runtime libraries. The
path is explicit in every run configuration.

## Create a run configuration

First calculate the input hash without relying on platform-specific shell
utilities:

```shell
uv run python -c "from hashlib import sha256; from pathlib import Path; p=Path('Pricing_20230927.gdx'); print(sha256(p.read_bytes()).hexdigest())"
```

Create `run.json`:

```json
{
  "formulation_id": "vspd-v5.0.6-reserve",
  "input_path": "/absolute/path/Pricing_20230927.gdx",
  "output_directory": "/absolute/path/results/20230927",
  "source_sha256": "replace-with-the-64-character-input-hash",
  "gams_system_directory": "/Library/Frameworks/GAMS.framework/Resources",
  "solver_profile": "scip-mip-fixed-highs-rmip",
  "input_schema": "vspd-v5.0.6",
  "case_ids": [],
  "maximum_solve_loops": 5,
  "price_rounding_decimals": 5,
  "worker_count": 1
}
```

Absolute paths make runs independent of the shell's working directory. The
output directory may not exist yet, but the input file and GAMS directory must
exist when the configuration is loaded.

## Run and inspect

```shell
uv run pyspd run --config run.json
```

A successful command prints JSON containing the final state, output directory,
and report-manifest hash. The output directory contains twelve CSV tables and
`manifest.json`.

Verify the written bundle using the same hash checks used by the application:

```shell
uv run python -c "from pathlib import Path; from pyspd.reporting import ReportBundle; b=ReportBundle.read(Path('/absolute/path/results/20230927')); print(b.provenance.logical_sha256, sorted(b.tables))"
```

Then read [how to run subsets and full days](user-guide/running.md) and [how to
interpret the reports](user-guide/results.md).
