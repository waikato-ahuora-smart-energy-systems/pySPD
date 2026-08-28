# Gate 1 decision checklist

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Current decision | **HOLD — NOT CLOSED** |
| Review date | Not scheduled |

| ID | Criterion | Current evidence | State |
|---|---|---|---|
| `G1-01` | Clean fixture reproduction | Class-based runner; frozen nine-case SPD corpus plus AUD; every run hash-bound | Partial: designated 546-interval population open |
| `G1-02` | Determinism and basis sensitivity | Two clean runs have identical solve, price, canonical GDX, dictionary, solution, and matrix logical hashes; basis perturbation open | Partial |
| `G1-03` | All in-scope branches/reports represented | DPS, nine SPD RTD/PRSS fixtures, AUD standard/audit reports | **Hold**: remaining preprocessing and solve branches open |
| `G1-04` | Historical packs classified and reproduced | 2023 pack hash-bound and deferred as RTP-v4; all nine in-scope 2025 RTD/PRSS inputs executed; three NRSS/NRSL inputs deferred | Met |
| `G1-05` | Small repository GDX is smoke-only | Explicitly classified | Met |
| `G1-06` | Semantic matrix export | GAMS Convert DumpGDX/DictMap export and validation for all ten frozen runs | Met for frozen corpus |
| `G1-07` | Preprocessing checkpoints | Three raw- and canonical-hash-bound checkpoints; instrumented/control runs have identical solve, report, price, solution, matrix, and dictionary semantics | Met |
| `G1-08` | Per-solve structural/solution snapshots | Complete ordinal/model/type-bound pre/post GDX pairs for every MIP/RMIP invocation; fail-closed pair inventory | Partial: per-invocation semantic matrix/name dictionaries open |
| `G1-09` | Approved SPD/AUD overlay | Typed, hash-bound, fail-closed overlay executed for SPD and AUD; named AUD source compatibility patch | Met |
| `G1-10` | Approved MIP/final-LP price convention | 38 optimal SCIP MIPs followed by 38 optimal fixed-discrete HiGHS RMIPs; 20,344 prices independently reproduced | Met for frozen corpus; finite-difference cases remain part of branch coverage |
| `G1-11` | Comparator mathematics frozen | Exact hashes plus frozen activity/bound/raw-and-scaled-stationarity and node-price/price-transfer equations | Partial: incremental row/dual transforms and complementarity open |
| `G1-12` | Official secondary comparisons | All nine in-scope 2025-pack cases compared by unambiguous keys; differences classified as CPLEX solver-profile divergence under ADR-0008 | Met |
| `G1-13` | Calibrated tolerances | Current matrix, objective, native-price, and report thresholds empirically frozen with analytic tests | Partial: incremental/complementarity thresholds open |
| `G1-14` | Performance baseline | Initial wall-time observations only | Partial |
| `G1-15` | Independent review and approval | Not required by project direction; see ADR-0009 | Not applicable |

Gate 1 now has complete named-pack recovery and materially broader RTD/PRSS/AUD
evidence. The [closure decision](closure-decision.md) records the remaining
technical blockers. Stage 2 production work remains unauthorized until the
mandatory holds are closed or the governing plan is formally changed.
