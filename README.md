# pySPD

**New Zealand electricity dispatch and pricing in Python.**

pySPD is a class-based [Pyomo](https://www.pyomo.org/) implementation of New
Zealand's Scheduling, Pricing, and Dispatch model. Use it to replay vSPD inputs,
inspect dispatch and prices, and build reproducible market studies with explicit
input, solver, and report provenance.

[Get started](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/getting-started.md) ·
[Documentation](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/index.md) ·
[Case studies](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/case-studies/index.md) ·
[Validation status](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/reference/limitations.md)

> [!IMPORTANT]
> pySPD is an engineering candidate under staged validation. Retained comparisons
> support specific dates, formulations, and report surfaces; complete historical
> parity is not established. The qualified execution environment is Python 3.13
> on macOS ARM64.

## What it does

- Reads v5-style pricing GDX and legacy v3 final-pricing inputs through explicit
  schema adapters.
- Assembles energy, AC/HVDC network, reserve, and version-specific algebra from
  typed model components.
- Solves dispatch with SCIP, then fixes discrete/SOS state and prices the
  resulting continuous model with HiGHS.
- Checks physical residuals, objectives, prices, and reports independently.
- Writes twelve deterministic CSV tables and a SHA-256-bound `manifest.json`.
- Runs independent pricing cases in parallel and supports audited
  counterfactuals through a lower-level Python API.

```text
GDX → schema validation → preprocessing → Pyomo model
    → SCIP dispatch → fixed-discrete HiGHS pricing
    → independent validation → prices and report bundle
```

## Installation

Install in a Python 3.13 environment:

```shell
pip install pyspd
```

SCIP (`pyscipopt`) and HiGHS (`highspy`) install automatically with pySPD.
For GDX input support, use `pip install "pyspd[gdx]"` and configure your local
GAMS runtime. The `clp`, `cbc`, and `probity` extras enable additional APIs and
solver profiles. See the [installation guide](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/getting-started.md).

## Quick start

For a guided introduction, use the [Jupyter notebook examples](examples/notebooks/README.md).
Six self-contained notebooks cover dispatch, prices, sensitivity, congestion,
reserve, and battery storage using `pyspd==0.1.0`. The seventh, **Entire NZ grid
setup**, consumes your GDX input, solves all cases and periods, and returns the
full results solution ZIP. The six synthetic examples include worked outputs
and numerical checks; the grid notebook requires your input.
An eighth adds scheduled battery and PV effects at chosen nodes: edit the node
and capacity settings, then download complete baseline and scenario solutions.

The qualified execution environment is **macOS ARM64 with Python 3.13**. Install
[uv](https://docs.astral.sh/uv/) and a local GAMS runtime, then obtain a
vSPD-compatible GDX input. GAMS provides GDX access; the normal solve uses SCIP
and HiGHS and does not require CPLEX.

```shell
git clone https://github.com/waikato-ahuora-smart-energy-systems/pySPD.git
cd pySPD
uv sync --frozen --group gdx
uv run pyspd formulations --json
```

Create `run.json`, replacing the paths and SHA-256 with your own values:

```json
{
  "formulation_id": "vspd-v5.0.6-reserve",
  "input_path": "/absolute/path/Pricing_20230927.gdx",
  "output_directory": "/absolute/path/results/20230927",
  "source_sha256": "replace-with-the-64-character-input-sha256",
  "gams_system_directory": "/Library/Frameworks/GAMS.framework/Resources",
  "case_ids": [],
  "worker_count": 1
}
```

The default schema is `vspd-v5.0.6` and the default solver profile is
`scip-mip-fixed-highs-rmip`. An empty `case_ids` list selects the complete
supported day; selecting one known case is a faster first check.

```shell
uv run pyspd run --config run.json
# For a full day on a host with sufficient memory:
uv run pyspd run --config run.json --workers 10
```

The [first-run guide](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/getting-started.md) includes input hashing, case
inventory, a configuration generator, and output verification.

## Choose a workflow

| Goal | Guide |
|---|---|
| Install and verify a first run | [Getting started](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/getting-started.md) |
| Configure a case, day, or solver profile | [Configuration](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/user-guide/configuration.md) and [CLI reference](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/reference/cli.md) |
| Understand dispatch and published prices | [Results and prices](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/user-guide/results.md) |
| Change demand, offers, outages, or reserves | [Case studies](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/case-studies/index.md) and [audited scenarios](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/user-guide/audited-scenarios.md) |
| Assess a historical comparison | [Validation](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/validation/index.md) and [interpreting parity](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/validation/interpreting-parity.md) |
| Extend the model | [Architecture](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/private/docs/developer-guide/architecture.md) |

The production formulations are `vspd-v5.0.6-reserve` and `spd-v16.0-reserve`.
The [multi-period battery study](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/case-studies/battery-storage.md) is a
separate analytic research profile. See [current limitations](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/reference/limitations.md)
for input, platform, scenario, and historical-report boundaries.

## External evidence

Large historical inputs and detailed CPLEX/solver observations are kept as
immutable, hash-bound release assets:

```shell
uv run pyspd evidence list
uv run pyspd evidence fetch cplex-reference-v1 --destination .
```

Ordinary tests do not download archives. Missing external evidence produces an
explicit skip, which is not a passing oracle result. The
[external evidence guide](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/docs/validation/external-evidence.md) explains archive
selection, authentication, caching, and verification.

## Build the documentation

The Read the Docs site uses Sphinx with the Read the Docs theme and the `docs` dependency group:

```shell
uv sync --frozen --group docs
uv run --no-sync sphinx-build -W --keep-going -b html docs site
uv run --no-sync python -m http.server 8765 --bind 127.0.0.1 --directory site
```

See [maintaining the documentation](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/private/docs/developer-guide/documentation.md) for
site structure, build configuration, and evidence-file handling.

## Development

```shell
uv sync --frozen --group docs
uv run --no-sync ruff check .
uv run --no-sync mypy src tools
uv run --no-sync pytest -q
uv run --no-sync python -m tools.probity_audit
uv run --no-sync sphinx-build -W --keep-going -b html docs site
git diff --check
```

The default dependency groups include development tools, HiGHS, CLP, and CBC.
Add `--group gdx` when the work needs GDX access. Model-affecting changes follow
[Probity TDD](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/private/docs/developer-guide/testing-and-evidence.md): preserve the failing
test before implementation and retain the red/green evidence with its
requirement, environment, and commits.

Internal engineering records are maintained in [private/](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/private/README.md),
separately from the user documentation published to Read the Docs.

## Licence

pySPD is licensed under the [Apache License 2.0](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/v0.1.2/LICENSE). Third-party
dependencies, external input data, and solver runtimes retain their own terms.
