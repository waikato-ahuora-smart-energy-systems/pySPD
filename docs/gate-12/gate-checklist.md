# Gate 12 checklist

| ID | Exit criterion | Current evidence | Status |
|---|---|---|---|
| `G12-01` | Exactly 546 unique affected identities across all 139 Gate 1 hashes | All 139 hashes screened; 434 diagnostic candidates and a 112-count gap recorded without claiming membership; corrected daily-mode benchmark completed 305/305 optimal broad-surface cases and is explicitly excluded; exact RTD-only shard execution is in progress | In progress |
| `G12-02` | All 546 cases replayed through pinned GAMS and PySPD | Prefix-complete PySPD replay planner implemented and tested; execution waits for the exact population manifest | Pending execution |
| `G12-03` | Complete normal, outage, high/negative-price, scarcity, islanding, 46-period, and 50-period days | Required categories enforced by `Gate12EvidenceIndex`; Gate 1 DST inputs are hash-bound | Pending execution |
| `G12-04` | Identical selection, order, prior-dispatch initialization, and fallback path | Historical checkpoints require exact canonical GDX progress order; application selection fails on missing/duplicate identities; replay plans include the canonical same-day prefix through the last affected case; cross-implementation state-transition comparison remains pending | Partial |
| `G12-05` | Primary physics, objective, and fixed-discrete pricing state parity | Portable v16 representative objective and independent validation pass | Partial |
| `G12-06` | Raw/repaired/node/reserve/published price parity or valid case-specific certificate | Portable v16 reserve certificate passes; 389 v16 node prices remain unresolved | Open |
| `G12-07` | Every in-scope report identity and field compared | Report-field surface and report hashes are mandatory in the closure index | Pending execution |
| `G12-08` | Repeat and checkpoint/resume equality | Hash-qualified atomic population resume implemented; whole-day repeat/resume output equality mandatory | Partial |
| `G12-09` | SCIP-MIP → fix discrete → HiGHS-RMIP portable profile passes | Application configuration now explicitly selects and hashes `scip-mip-fixed-highs-rmip`; representative v5/v16 pathways and independent validators pass; complete population/day execution pending | Partial |
| `G12-10` | Strict historical CPLEX profile executed | Installed command-line GAMS licence does not entitle CPLEX; GAMSPy-only licence cannot execute the existing `$include`-based GAMS source | Blocked on compatible CPLEX execution entitlement |
| `G12-11` | Source, configuration, code, dependency, solver, result, comparison, and report hashes indexed | Fail-closed `Gate12EvidenceIndex` and per-day raw-artifact hash contract implemented | Pending final evidence |
| `G12-12` | Zero unresolved material discrepancies | Closure index rejects any non-zero discrepancy count | Pending |

Gate 12 remains open until every row is met. No separate independent human
reviewer or approval is required, but no pending, partial, or blocked row may be
treated as passing evidence.
