# Period-to-period warm-start trial — 2022-11-06

PySPD now has opt-in, period-neutral primal snapshots. A snapshot remaps the
case/date dimensions to the canonical successor, rejects missing, non-finite,
out-of-bound, and non-integral values, and can independently seed SCIP's
integer MIP start or HiGHS' primal start. The normal application path remains
cold.

The controlled comparison used the first four consecutive cases from the
hash-pinned `Pricing_20221106.gdx`. It ran twice in alternating order:
cold→SCIP-warm, then SCIP-warm→cold. Each SCIP-warm successor received 12
matching integer values. All primary SCIP and fixed-state HiGHS solves reported
optimal.

| Metric | Cold | SCIP discrete warm start | Change |
|---|---:|---:|---:|
| Median four-case solve wall time | 77.474 s | 77.838 s | 0.469% slower |
| Mean of the six actually warmed case solves | 20.052 s | 19.995 s | 0.282% faster |
| Result hash | `4bfc69f…` | `4bfc69f…` | Exact |

The parity comparator checked 15,224 values. Objectives, physics, prices,
fixed-discrete state, identities, and published output were exactly equal.
Input reading and case preparation took another 43.395 s, or 35.90% of the
cold measured end-to-end total. Including that shared preparation cost, the
SCIP warm path was 0.30% slower. The observed changes are within run-to-run
noise and do not establish a useful warm-start speedup.

An earlier two-case exploratory run also seeded the fixed-RMIP with all 56,870
available SCIP primal values. It was 7.01% slower and selected a different raw
dual on a degenerate price surface, although fixed state and published output
were unchanged. HiGHS primal warm starting is therefore not suitable for the
qualified pricing path.

Decision: retain the class-level warm-start capability and reproducible
benchmark as opt-in diagnostics, but do not enable either warm path by default.
The next performance work should target GDX/case preparation, Pyomo model
construction, and carefully invalidated persistent solver reuse.

The complete machine-readable record is
[`warm-start-trial-20221106.json`](warm-start-trial-20221106.json).
