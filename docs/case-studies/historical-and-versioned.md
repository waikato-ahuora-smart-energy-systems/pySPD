# Historical and versioned studies

## Legacy 2019 final-pricing input

Select the legacy schema explicitly:

```json
{
  "formulation_id": "vspd-v5.0.6-reserve",
  "input_path": "/data/FP_20190218_F.gdx",
  "output_directory": "/results/20190218/base",
  "source_sha256": "...",
  "gams_system_directory": "/Library/Frameworks/GAMS.framework/Resources",
  "input_schema": "vspd-v3-final-pricing",
  "solver_profile": "scip-mip-fixed-highs-rmip",
  "worker_count": 10
}
```

The adapter handles governed symbol and unit differences, including the legacy
ramp-rate conversion. It does not recreate unsupported legacy daily aggregate
tables such as every historical SystemResults or TraderResults field. Compare
only implemented mapped surfaces.

## SPD formulation v16

Use:

```json
{
  "formulation_id": "spd-v16.0-reserve",
  "input_schema": "vspd-v5.0.6"
}
```

The source date must be on or after 23 June 2026. The compatibility policy
fails closed for earlier sources; do not relabel an older GDX to bypass it.

For a v5-versus-v16 comparison, hold the source population constant only when
the source is valid for both profiles. Compare formulation-specific domains,
objective terms and report mappings before numerical output. A result delta is
not attributable to “v16” until data and solver differences have been excluded.

## GAMS oracle replay

Oracle tooling requires the `oracle` dependency group, installed GAMS runtime,
the correct source checkout/includes, and suitable solver entitlement:

```shell
uv sync --frozen --group oracle
```

GAMSPy can read GDX and run GAMSPy-native models, but a GAMSPy entitlement does
not automatically license every solver invoked by existing `$include`-based
GAMS source. Record the actual executable, solver, option files, source-tree
hash, and license boundary for each oracle run.

## CPLEX archive comparison

Treat the supplied historical CPLEX files as the designated output standard,
while recognizing what they store:

- many legacy values are rounded to displayed precision;
- solver bases and MIP termination state are not fully preserved;
- zero-flow and reserve kinks can have non-unique prices; and
- some old aggregate tables have no current PySPD counterpart.

Use the mapped-field comparator, preserve missing/extra identities, and accept a
price only if it matches display precision or lies in a governed analytical
interval. Never choose a solver rerun after observing which endpoint matches.

## Residential-PV counterfactuals

Use [audited demand overrides](demand-and-offers.md) to explore changes in net
node demand. Retain the PV dataset, node mapping, units, and scenario definition
with the results. Generic demand scaling does not establish replication of a
published residential-PV study; that requires matching its method and data.
