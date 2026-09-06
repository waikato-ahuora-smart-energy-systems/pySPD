# Configuration fields

`ApplicationConfiguration.from_json` rejects unknown fields. Paths are expanded
and resolved during construction.

Relative paths are resolved against the process's current working directory,
not the directory containing the JSON file. Use absolute paths when running a
configuration from another directory.

| Field | Type | Required | Default | Meaning |
|---|---|---:|---|---|
| `formulation_id` | string | yes | — | Explicit registered model formulation |
| `input_path` | path | yes | — | Existing source GDX |
| `output_directory` | path | yes | — | Report target directory |
| `source_sha256` | string | yes | — | Exact SHA-256 of `input_path` |
| `gams_system_directory` | path | yes | — | Existing GAMS runtime directory |
| `solver_profile` | string | no | `scip-mip-fixed-highs-rmip` | Primary/pricing solver chain |
| `input_schema` | string | no | `vspd-v5.0.6` | Explicit GDX schema/adapter |
| `case_ids` | array[string] | no | `[]` | Unique case membership filter |
| `maximum_solve_loops` | integer | no | `5` | Positive application shortfall-loop bound |
| `price_rounding_decimals` | integer | no | `5` | Publication decimals from 0 through 12 |
| `worker_count` | integer | no | `1` | Positive independent process count |

## Formulation IDs

```text
vspd-v5.0.6-reserve
spd-v16.0-reserve
```

Discover the registered set from the installed code:

```shell
uv run pyspd formulations --json
```

## Input schemas

```text
vspd-v5.0.6
vspd-v3-final-pricing
```

The input schema is not auto-detected. `vspd-v3-final-pricing` cannot be paired
with `spd-v16.0-reserve`.

## Solver profiles

| Profile | MIP | Fixed RMIP | Use |
|---|---|---|---|
| `scip-mip-fixed-highs-rmip` | SCIP | HiGHS | Qualified default |
| `scip-mip-fixed-clp-rmip` | SCIP | CLP | Independent pricing validation |
| `cbc-mip-fixed-highs-rmip` | CBC | HiGHS | Experimental MIP comparison |
| `cbc-mip-fixed-clp-rmip` | CBC | CLP | Experimental combined comparison |

Profiles are explicit. PySPD does not silently substitute an available solver
when the requested one is missing.

## Hash behavior

The logical application-configuration hash includes formulation, input name and
schema, source hash, selected cases, solve-loop bound, rounding, solver profile,
and worker count. It excludes machine-specific input/output/system-directory
paths so an otherwise identical run can be staged on another host.

The CLI `--workers` override creates a new effective configuration and therefore
a different configuration hash.
