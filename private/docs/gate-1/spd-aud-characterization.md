# Gate 1 SPD/AUD characterization

| Field | Value |
|---|---|
| Date | 29 August 2026 |
| Input | `RTD_202502261155_251012025022255930_20250226115400.gdx` |
| Input SHA-256 | `f010065a800a0c48a1147fd3543d372eaa65acc9e0f0ed6ea64546a474655c65` |
| Source | vSPD v5.0.6, commit `21b1cf33f5607399331dcb1c03270348def5ccc8` |
| Profile | SCIP MIP → fixed-discrete HiGHS RMIP |
| Result | SPD and AUD qualified for this fixture |

## Configuration overlay

`VspdRunConfiguration` permits only `SPD`, `AUD`, and `DPS`, rejects unsafe run
names, and records a deterministic logical hash. The runner replaces exactly one
`runName` and one `opMode` setting in a staged source copy; a missing or changed
source anchor fails the run. It cannot silently retain the pinned source's
default `DPS` mode.

| Mode | Run name | Overlay logical SHA-256 | Source patch |
|---|---|---|---|
| SPD | `gate1_spd_pricing_rtd_202502261155` | `b3821fd49c5af80431d16108455a028e3b110b09b3656faa633ba81e15c4047b` | None |
| AUD | `gate1_aud_pricing_rtd_202502261155` | `7f03e7775425447627774dd06414f5d6bed06e78add45a66a5066f27e3510d12` | `vspd-v5.0.6-audit-o-bus-alias-v1` |

The pinned `vSPDreport.gms` AUD branch refers to undeclared `o_bus` while the
declared set is `bus`. The AUD overlay replaces that one exact expression in the
staged copy. The named compatibility patch is AUD-only, hash-bound, and fails
closed if the source no longer matches.

## Execution evidence

Both modes reported normal completion and optimal model status for one SCIP MIP
and one fixed-discrete HiGHS RMIP. Their primary and pricing objectives were
`83427992.0229` NZD. GAMS Convert then emitted one non-optimizing matrix export.

| Evidence | SPD | AUD |
|---|---:|---:|
| Standard report files | 13 | 13 |
| Audit CSV files | 0 | 6 |
| Audit `AllData.gdx` | 0 | 1 |
| Total report artifacts | 13 | 20 |
| Report logical SHA-256 | `1a2b817eaa2a5e50556b51664c74df7a6fcb022f5bf81f8a78423161f0c682ed` | `d009f7e090966d9387cbf1edb98869a52e6dfe6f5f3f3cbed2a5fd9ca4c6e705` |
| Published price records | 534 | 534 |
| Published-price logical SHA-256 | `8e47d8834659f5e407e5a059869cde432b7d2d8d5748dc6e8d8710345d768633` | Same |

The normal and audit runs have identical logical solve records, standard CSV
hashes, canonical matrix evidence, and independent price evidence. AUD changes
only the expected audit report family.

## Canonical matrix and independent prices

The fixed RMIP has 33,131 rows, 58,232 columns, and 111,925 nonzeros. Independent
validation measured maximum activity delta `7.88e-11`, row-bound violation
`1.28e-9`, no column-bound violation, and stationarity residual `1.19e-9`, all
inside the `1e-7` acceptance threshold.

The node-price validator does not consume `o_nodePrice_TP` to construct prices.
It retains raw `ACnodeNetInjectionDefinition2` marginals, materializes GAMS'
sparse `busPrice` parameter over the balance-bus universe, and independently
applies `nodeBusAllocationFactor`. This reproduces vSPD's disconnected-bus
post-processing, including sparse zero prices. For both modes:

- 534 node prices were reconstructed;
- 152 bus prices differ from the raw balance marginal after vSPD
  post-processing;
- native-GDX maximum absolute node-price delta is zero; and
- five-decimal report maximum absolute delta is `4.993e-6` NZD/MWh.

## Official secondary output

The Authority-supplied `RTD_202502261155` CPLEX report is retained as a secondary
comparison, not as the active oracle under ADR-0008. Two of thirteen CSV files
are byte-identical. The published-energy-price files have the same 534 keys;
364 values are exact and 170 differ. The maximum difference is
`184.79089` NZD/MWh at `BLN0331`, while the reported system objective differs by
only `0.00001` NZD.

This is classified as a solver-profile pricing divergence: SCIP/HiGHS results
are internally validated against the exported fixed RMIP, but they do not prove
CPLEX dual parity. CPLEX-specific price parity remains deferred by ADR-0008 and
must not be claimed from this evidence.

## Remaining qualification boundary

This evidence closes the explicit SPD/AUD overlay and report-family blocker for
the selected RTD fixture. It does not cover all historical inputs,
preprocessing branches, solve/re-solve paths, checkpoint instrumentation,
feature-disabled matrix projections, basis sensitivity, or corpus-wide
tolerance calibration.
