# PySPD

PySPD is a class-based Pyomo implementation of the Electricity Authority's
vectorised Scheduling, Pricing, and Dispatch model. The current engineering
candidate implements the explicitly selected `vspd-v5.0.6-reserve`
formulation and uses SCIP MIP followed by a fixed-discrete HiGHS RMIP solve.

This repository is under staged validation. Public distribution is held until
the Gate 0 legal and licensing decisions are complete. Strict end-to-end
parity, full-day qualification, and CPLEX validation are reserved for Gate 12.
Stage 13 is a planned, separately named research profile to reproduce the
residential-PV counterfactual study in O'Leary, Atkins, and Severinsen (2026)
after its full methods and source data have been acquired and hash-bound.

## Set up with uv

```shell
uv sync --frozen --group oracle
uv run pyspd formulations --json
uv run pytest -q
```

Run a case from a hash-bound JSON configuration:

```shell
uv run pyspd run --config path/to/config.json
uv run pyspd run --config path/to/config.json --workers 10
```

The configuration selects a named formulation, input GDX, cases, solver
profile, output directory, and a positive `worker_count` (default `1`). The
CLI `--workers` option overrides that value for a run. Multi-worker execution
uses dynamically assigned isolated case processes and preserves canonical
source/report order; use fewer workers when memory headroom is limited.
Generated report manifests bind source, configuration, dependency, solver,
worker count, and environment provenance.

The controlled delivery scope and evidence boundaries are defined in
[`docs/pyomo-vspd-stage-gate-plan.md`](docs/pyomo-vspd-stage-gate-plan.md).
The Stage 13 source-entry pack is in
[`docs/gate-13/README.md`](docs/gate-13/README.md).

## Documentation

The user guide, case-study recipes, report reference, validation guidance, and
developer extension guide start at [`docs/index.md`](docs/index.md). Build the
Read the Docs site locally with:

```shell
uv sync --frozen --group docs
uv run mkdocs serve
```

Use `uv run mkdocs build --strict` for the same fail-on-warning build used by
CI and Read the Docs.
