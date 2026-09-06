# Configuration

`pyspd run` accepts one hash-bound JSON document. Unknown keys are rejected,
paths are resolved, case identifiers must be unique, and the input file's
actual SHA-256 must equal `source_sha256`.

## Minimal configuration

```json
{
  "formulation_id": "vspd-v5.0.6-reserve",
  "input_path": "/data/Pricing_20230927.gdx",
  "output_directory": "/results/base-20230927",
  "source_sha256": "c854...64-hex-characters...",
  "gams_system_directory": "/Library/Frameworks/GAMS.framework/Resources"
}
```

Omitted optional fields receive the defaults shown in the [configuration
reference](../reference/configuration.md).

## Formulation and input schema are separate

`formulation_id` selects model algebra. `input_schema` selects how the GDX is
interpreted. They are never inferred from a filename or date.

| Input | `input_schema` | Compatible formulation |
|---|---|---|
| v5-style pricing GDX | `vspd-v5.0.6` | `vspd-v5.0.6-reserve` |
| Legacy 2019 final-pricing GDX | `vspd-v3-final-pricing` | `vspd-v5.0.6-reserve` |
| SPD v16 source | `vspd-v5.0.6` | `spd-v16.0-reserve` |

The legacy adapter normalizes historical symbol names and units before the
v5-compatible model is built. Legacy input is deliberately rejected for the
SPD v16 formulation.

## Selecting cases

An empty `case_ids` array selects every supported case in source time order.
To run a subset, copy exact identifiers from the GDX inventory:

```json
"case_ids": [
  "211012023091330496",
  "211012023091330497"
]
```

The requested array is a membership filter; execution is restored to canonical
source/date order. A missing or duplicate identifier fails before solving.

## Solver profiles

Use `scip-mip-fixed-highs-rmip` for qualified normal work. The other accepted
names exist for explicit experiments:

- `scip-mip-fixed-clp-rmip`;
- `cbc-mip-fixed-highs-rmip`; and
- `cbc-mip-fixed-clp-rmip`.

CBC and CLP require their optional `uv` groups. A different profile can select
a different valid discrete support or dual basis, so comparisons must retain
the solver profile in their evidence.

The repository's default dependency groups already include `highs`, `clp`,
`cbc`, and `dev`. Only add a solver group explicitly when installing with
`--no-default-groups` or documenting a particular experiment.

## Parallelism

Set `worker_count` in JSON or override it for one invocation:

```shell
uv run pyspd run --config run.json --workers 10
```

The effective worker count is included in the application configuration hash.
Each worker runs single-threaded SCIP and HiGHS in an isolated process. Ten
workers improved full-day throughput on the qualification host; three workers
remain the lower-memory choice. PySPD fails closed if a planned worker boundary
would discard required predecessor-generation state.

## Output isolation

Give every scenario its own output directory. Report writing replaces files of
the same names in that directory, so do not point two concurrent runs at one
target. A useful hierarchy is:

```text
results/
  20230927/
    base/
    demand-plus-5pct/
    hvdc-outage/
```

Keep the input GDX, configuration JSON, scenario definition, console log, and
result manifest together when producing evidence.
