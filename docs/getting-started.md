# Getting started

This guide takes a repository checkout to a verified dispatch and pricing
report bundle. You need your own vSPD-compatible GDX input; historical inputs
are distributed separately from the source repository.

## Installing from PyPI

Install in a separate study environment. On the qualified
macOS ARM64/Python 3.13 profile:

```shell
mkdir pyspd-study
cd pyspd-study
uv venv --python 3.13
uv pip install --python .venv/bin/python "pyspd[gdx]"
.venv/bin/pyspd formulations --json
```

SCIP (via `pyscipopt`) and HiGHS (via `highspy`) are required dependencies and
install automatically with PySPD. No solver extra or separate solver installation
is needed on the supported macOS ARM64 platform. The `gdx` extra installs the
Python GDX adapter dependencies; you still supply the local GAMS runtime
location. Optional extras `clp` and `cbc` enable alternative solver profiles.
The `probity` extra is only needed for the standalone evidence-validation API.

Prepare a configuration using the instructions below, then run
`.venv/bin/pyspd run --config run.json`. In this environment, use
`.venv/bin/python` for the Python examples. The `uv sync` and `uv run` commands
elsewhere in the manual describe working from a repository checkout.

## Installing a candidate wheel

To test a supplied wheel before publication, replace `"pyspd[gdx]"` in the
installation command above with `"/path/to/pyspd-0.1.0-py3-none-any.whl[gdx]"`.

## 1. Prepare the environment

The currently qualified execution profile is **macOS ARM64, Python 3.13**.
Install [uv](https://docs.astral.sh/uv/) and a local GAMS runtime for GDX access.
Other operating systems are not qualified by the retained CI evidence. Building
this documentation does not require a GAMS installation.

```shell
git clone https://github.com/waikato-ahuora-smart-energy-systems/pySPD.git
cd pySPD
uv sync --frozen --group gdx
uv run pyspd formulations --json
```

If you already have a checkout, start at `uv sync`. The discovery command should
return:

```json
{"formulations": ["spd-v16.0-reserve", "vspd-v5.0.6-reserve"]}
```

`uv.lock` defines the dependency versions. The default groups install development
tools, HiGHS, CLP, and CBC; `--group gdx` adds the GAMSPy/GAMS Transfer dependency.
SCIP performs the MIP dispatch solve and HiGHS performs fixed-discrete pricing.
The normal pathway does not execute the original GAMS model or require CPLEX.

## 2. Locate the input and GAMS runtime

Choose a **v5-style pricing GDX** for this walkthrough. For a legacy v3 input or
SPD v16 study, first read the [schema and formulation
mapping](user-guide/configuration.md#formulation-and-input-schema-are-separate).

Set `gams_system_directory` to the directory containing the GAMS executable and
runtime libraries. A macOS framework installation commonly uses:

```text
/Library/Frameworks/GAMS.framework/Resources
```

Check your installed location. PySPD requires an existing, explicitly named
runtime directory. A GDX input directory or a GAMS model checkout is not the
runtime directory.

If you need a retained validation input, use the [external evidence
guide](validation/external-evidence.md) to choose and restore an archive. The
commands below do not download one automatically.

## 3. Select the cases

[Inventory the GDX](user-guide/inputs-and-gdx.md#inventory-cases-before-a-study)
and copy an exact case ID for a small first run. An empty `case_ids` list runs
all supported cases in the input, which can mean hundreds of solves and large
report files.

Case IDs are not trading-period numbers. Several cases may contribute to one
published trading-period price; a one-case result is useful for diagnosis but
may not reproduce that complete publication.

## 4. Generate a configuration with the actual input hash

From the repository root, run this snippet after replacing the three paths and
optionally adding a known case ID. It writes `run.json` in the current directory:

```shell
uv run python - <<'PY'
import hashlib
import json
from pathlib import Path

input_path = Path("/absolute/path/Pricing_20230927.gdx").expanduser().resolve()
output_directory = Path("/absolute/path/results/first-run").expanduser().resolve()
gams_directory = Path("/Library/Frameworks/GAMS.framework/Resources").resolve()

with input_path.open("rb") as source:
    source_sha256 = hashlib.file_digest(source, "sha256").hexdigest()

configuration = {
    "formulation_id": "vspd-v5.0.6-reserve",
    "input_path": str(input_path),
    "output_directory": str(output_directory),
    "source_sha256": source_sha256,
    "gams_system_directory": str(gams_directory),
    "solver_profile": "scip-mip-fixed-highs-rmip",
    "input_schema": "vspd-v5.0.6",
    "case_ids": [],  # Put a known case ID here for a smaller first run.
    "worker_count": 1,
}
Path("run.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
print(source_sha256)
PY
```

Keep the source GDX unchanged after generating the configuration. PySPD rejects
a hash mismatch. Use a distinct output directory for each run: report writing
replaces files of the same name.

For a hand-written JSON example, see [configuration](user-guide/configuration.md).
The [field reference](reference/configuration.md) lists every accepted key and
default. Relative paths resolve against the working directory, so the snippet
uses absolute paths.

## 5. Run PySPD

```shell
uv run pyspd run --config run.json
```

The CLI prints a JSON result containing `state`, `output_directory`, and
`report_manifest_sha256`. A successful run has `state: "complete"`.

After a one-worker run succeeds, a full day can use independent worker processes:

```shell
uv run pyspd run --config run.json --workers 10
```

Select workers according to memory capacity. Each solver process is
single-threaded, and more workers can be slower if the host starts swapping.
See [running cases and days](user-guide/running.md) for predecessor-state
boundaries, publication groups, and logging.

## 6. Verify and inspect the report bundle

The output directory contains `manifest.json` and twelve CSV tables. Read it
through PySPD to verify file hashes, row counts, schemas, and the logical
manifest hash before interpreting values:

```shell
uv run python - <<'PY'
import json
from pathlib import Path

from pyspd.application import ApplicationConfiguration
from pyspd.reporting import ReportBundle

configuration = ApplicationConfiguration.from_json(Path("run.json"))
output = configuration.output_directory
bundle = ReportBundle.read(output)
manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

print("Report manifest:", manifest["logical_sha256"])
print("Tables:", ", ".join(sorted(bundle.tables)))
summary = bundle.tables["summary"].rows
print("Cases:", len(summary))
print("Status codes:", sorted({row["status_code"] for row in summary}))
PY
```

Compare the printed **report manifest** hash with the CLI's
`report_manifest_sha256`. `bundle.provenance.logical_sha256` is a different
hash: it identifies provenance metadata rather than the complete report bundle.

Start with `summary.csv` and `audit.csv`. Require status code `1` for each case
and inspect violation quantities before using prices or economic results. Bundle
integrity alone does not establish physical validity or historical parity.
`ReportBundle.read` loads all tables into memory; large full-day bundles may
need substantial memory, particularly for `constraint.csv`.

## Continue from a working baseline

| Next task | Guide |
|---|---|
| Understand bus, node, reserve, and published prices | [Results and prices](user-guide/results.md) |
| Change demand, offers, or network assumptions | [Choose a case study](case-studies/index.md) |
| Compare against historical results | [Interpreting parity](validation/interpreting-parity.md) |
| Look up commands or configuration keys | [CLI](reference/cli.md) and [configuration fields](reference/configuration.md) |
| Resolve an installation or solve failure | [Troubleshooting](troubleshooting.md) |
