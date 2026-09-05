# Running PySPD

## Run one existing pricing case

First [inventory the GDX](inputs-and-gdx.md#inventory-cases-before-a-study).
Put one exact identifier in `case_ids` and use one worker:

```json
{
  "case_ids": ["211012023091330496"],
  "worker_count": 1
}
```

This is the fastest feedback loop for model development, price diagnosis, and
scenario prototyping. It still executes SCIP MIP followed by the fixed RMIP and
writes the complete report surface.

## Run a trading-period publication group

Modern daily GDX files may contain several pricing cases contributing to one
trading period. Select every contributing `case_id`, not merely the first case,
when the study needs the published price. `published_price.csv` weights each
case by its source `publication_seconds` and rounds only at the declared
publication boundary.

If a prefix or arbitrary subset is used, describe the result as a subset
publication. It is not the complete historical trading-period publication
unless all contributing cases are present.

## Run a complete day

Leave `case_ids` empty and select a process count appropriate to the host:

```shell
uv run pyspd run --config full-day.json --workers 10
```

Complete v5 days can contain hundreds of pricing scenarios, even though they
have 46, 48, or 50 trading periods. The application assigns one-case jobs to
the next idle worker and merges output in source order.

!!! note "Memory before cores"

    A representative complex process peaked near 4.2 GB during qualification.
    Peak use varies by case. Reduce workers if the host begins swapping; solver
    contention and memory pressure can make a larger process count slower.

## Run from Python

The application API is useful when a study needs programmatic configuration or
post-processing:

```python
from pathlib import Path

from pyspd.application import ApplicationConfiguration, PyspdApplication

configuration = ApplicationConfiguration.from_json(Path("run.json"))
run = PyspdApplication().run(configuration)

assert run.result.state.value == "complete"
print(run.report_manifest.logical_sha256)
print(run.output_directory)
```

For multi-worker runs, `CaseRunResult.accepted.solve_payload` is intentionally
`None` in the parent process. Full report rows are rendered inside each worker
before live Pyomo and solver objects are discarded. Use a one-worker diagnostic
run if code needs to inspect the live model graph.

## Safe reruns

For a formal repeat:

1. preserve the original configuration and manifest;
2. use a new empty output directory;
3. keep `uv.lock`, formulation, solver profile, and worker count unchanged;
4. read both bundles with `ReportBundle.read`; and
5. compare identities before comparing values.

Different worker counts should preserve physical results and canonical report
order, but may select another valid endpoint on a degenerate face. Apply the
[analytical-interval rules](../validation/interpreting-parity.md) rather than
silently rounding away such differences.

## Logs and failure handling

The CLI exits with code 2 for invalid configuration and data-boundary errors.
Solver or orchestration failures identify the affected job/case and do not
produce a falsely complete result. Capture stdout and stderr for long runs:

```shell
uv run pyspd run --config full-day.json --workers 10 2>&1 | tee full-day.log
```

The shell pipeline is convenient interactively; qualification automation
should also enable `pipefail` so a failing PySPD process cannot be hidden by a
successful `tee`.
