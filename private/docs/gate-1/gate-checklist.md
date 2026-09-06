# Gate 1 decision checklist

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Current decision | **PASS — CLOSED** |
| Review date | 29 August 2026 |

| ID | Criterion | Current evidence | State |
|---|---|---|---|
| `G1-01` | Clean fixture reproduction | Class-based runner; frozen nine-case SPD corpus plus AUD; all runs hash-bound; 139 corrected daily inputs date-qualified under ADR-0010 | Met |
| `G1-02` | Determinism and basis sensitivity | Two clean runs are logically identical; primal-simplex/no-presolve perturbation preserves structure/objective and classifies alternative optimal report primals/duals | Met |
| `G1-03` | All in-scope branches/reports represented | DPS, nine SPD RTD/PRSS fixtures, AUD standard/audit reports, exact affected transfer/max-loop/cleanup fixture, and 46/50-period fixtures | Met |
| `G1-04` | Historical packs classified and reproduced | 2023 pack hash-bound and deferred as RTP-v4; all nine in-scope 2025 RTD/PRSS inputs executed; three NRSS/NRSL inputs deferred | Met |
| `G1-05` | Small repository GDX is smoke-only | Explicitly classified | Met |
| `G1-06` | Semantic matrix export | GAMS Convert DumpGDX/DictMap export and validation for all ten frozen runs | Met for frozen corpus |
| `G1-07` | Preprocessing checkpoints | Three raw- and canonical-hash-bound checkpoints; instrumented/control runs have identical solve, report, price, solution, matrix, and dictionary semantics | Met |
| `G1-08` | Per-solve structural/solution snapshots | Complete ordinal/model/type-bound pre/post GDX state, semantic matrix, and scalar/name dictionary for every MIP/RMIP invocation; fail-closed inventory | Met |
| `G1-09` | Approved SPD/AUD overlay | Typed, hash-bound, fail-closed overlay executed for SPD and AUD; named AUD source compatibility patch | Met |
| `G1-10` | Approved MIP/final-LP price convention | 38 optimal SCIP MIPs followed by 38 optimal fixed-discrete HiGHS RMIPs; 20,344 prices independently reproduced; affected branch independently optimal | Met |
| `G1-11` | Comparator mathematics frozen | Exact semantic/scalar hashes; versioned Stage 4--7 projections; frozen activity, bounds, stationarity, dual-side, complementarity, node-price, and transfer equations | Met |
| `G1-12` | Official secondary comparisons | All nine in-scope 2025-pack cases compared by unambiguous keys; differences classified as CPLEX solver-profile divergence under ADR-0008 | Met |
| `G1-13` | Calibrated tolerances | Matrix, objective, native/report price, stationarity, dual-sign, and complementarity thresholds empirically frozen with analytic tests | Met |
| `G1-14` | Performance baseline | Controlled arm64 GAMS 54.3.1 phase/per-solve/wall/RSS baseline, including instrumentation overhead | Met |
| `G1-15` | Independent review and approval | Not required by project direction; see ADR-0009 | Not applicable |

Gate 1 is closed with no mandatory hold or unexplained oracle
self-inconsistency. The [closure decision](closure-decision.md) authorizes Stage
2. Exact identification and replay of all 546 shortfall-transfer intervals is
not waived; amended ADR-0010 assigns it to the mandatory Gate 12 criterion.
