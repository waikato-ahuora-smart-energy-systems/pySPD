# Troubleshooting

## `input source hash mismatch`

The GDX bytes differ from `source_sha256`. Recalculate the hash, then determine
why it changed. Update the configuration only when the new file is the intended
input; never bypass the check.

## GDX adapter dependencies are missing

For a repository checkout, install the optional data dependency:

```shell
uv sync --frozen --group gdx
```

For a wheel installation, reinstall the same wheel with its `gdx` extra as
shown in [getting started](getting-started.md#installing-a-candidate-wheel).

## PySPD build lock is missing

Reinstall the complete wheel. Its bundled build lock is required for report
provenance. Creating an unrelated `uv.lock` in the study directory does not
repair a damaged installation.

## GAMS system directory does not exist

Point `gams_system_directory` at the installed runtime directory, not a model
source checkout or a directory containing only `.gdx` files.

## Unknown or missing GDX symbols

Confirm `input_schema`. A 2019 final-pricing input normally needs
`vspd-v3-final-pricing`; a v5 input needs `vspd-v5.0.6`. If the schema is truly
new, add and validate an explicit adapter/catalog rather than renaming it.

## Missing requested case ID

Case IDs are exact and case-sensitive. Inventory the GDX source and copy the
complete identifier. Remember that one trading period can contain multiple
pricing case IDs.

## Parallel boundary requires predecessor generation

The case has no independently proven generation start at a worker boundary.
Run with `worker_count: 1`, select a prefix that includes its predecessor, or
implement a validated predecessor checkpoint. Do not force independence.

## Process run is slower or the machine swaps

Reduce workers. Three is the documented lower-memory setting; ten is useful
only for sufficiently large populations on a host with adequate memory.
Retain one solver thread per process.

## Pyomo clone warning about `solutions`

Some Pyomo versions warn that the solution container cannot be copied during a
model clone. The governed pricing path reconstructs the required container and
has completed qualified runs. Treat a changed warning or missing solution load
as a regression and rerun the relevant solver tests.

## CPLEX and PySPD both say optimal but differ

Compare source/config hashes, objective, violations, primal physics, and fixed
discrete/SOS state before duals. Then check display precision and reported
analytical intervals. If the reference lies outside an interval—or no interval
exists—the discrepancy remains unresolved until independently explained.

## Published price differs while case price matches

Check that all contributing cases were selected, their publication seconds are
present, datetimes map to the expected trading period, and rounding occurs only
after weighted aggregation. A subset run is not necessarily a complete
historical publication.

## Report bundle fails to read

`ReportBundle.read` fails on a changed CSV, row count, schema, or manifest hash.
Restore the immutable original bundle or rerun into a new directory. Do not edit
the manifest to bless changed output.

## Documentation build fails

```shell
uv sync --frozen --group docs
uv run sphinx-build -W --keep-going -b html docs site
```

Fix every warning. Read the Docs uses Python 3.13, installs dependencies with
`uv`, and builds from `docs/conf.py`.
