# Gate 1 decision checklist

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Current decision | **HOLD — NOT CLOSED** |
| Review date | Not scheduled |

| ID | Criterion | Current evidence | State |
|---|---|---|---|
| `G1-01` | Clean fixture reproduction | Class-based runner; repeated DPS and clean SPD/AUD RTD executions | Partial: corpus expansion open |
| `G1-02` | Determinism and basis sensitivity | Two clean runs have identical solve, price, canonical GDX, dictionary, solution, and matrix logical hashes; basis perturbation open | Partial |
| `G1-03` | All in-scope branches/reports represented | DPS plus normal SPD and AUD standard/audit reports for one RTD input | **Hold**: remaining preprocessing and solve branches open |
| `G1-04` | Historical packs classified and reproduced | Not recovered | **Hold** |
| `G1-05` | Small repository GDX is smoke-only | Explicitly classified | Met |
| `G1-06` | Semantic matrix export | GAMS Convert DumpGDX/DictMap export; 33,131 rows, 58,232 columns, and 111,925 nonzeros canonicalized reproducibly | Met for sample; corpus expansion open |
| `G1-07` | Preprocessing checkpoints | Not implemented | **Hold** |
| `G1-08` | Per-solve structural/solution snapshots | All solve statuses/objectives plus final-scenario fixed-LP solution, matrix, and name dictionary | Partial: per-scenario matrix snapshots open |
| `G1-09` | Approved SPD/AUD overlay | Typed, hash-bound, fail-closed overlay executed for SPD and AUD; named AUD source compatibility patch | Met |
| `G1-10` | Approved MIP/final-LP price convention | Explicit SCIP MIP to fixed-discrete HiGHS RMIP accepted by ADR-0008; independent final-scenario price and LP checks pass; CPLEX deferred | Met for sample; finite-difference/corpus evidence open |
| `G1-11` | Comparator mathematics frozen | Exact canonical hashes; objective tolerance; independent activity/bound/stationarity and node-price equations implemented | Partial: calibration evidence open |
| `G1-12` | Official secondary comparisons | Selected RTD official output compared; 170/534 CPLEX prices differ and are classified as deferred solver-profile divergence under ADR-0008 | Partial: corpus expansion open |
| `G1-13` | Calibrated tolerances | Candidate thresholds only | **Hold** |
| `G1-14` | Performance baseline | Initial wall-time observations only | Partial |
| `G1-15` | Independent review and approval | Not required by project direction; see ADR-0009 | Not applicable |

Gate 1 now has DPS, SPD, and AUD evidence for one RTD input, but the required
historical and branch corpus is not complete. The [closure decision](closure-decision.md) records the material
blockers. Stage 2 production work remains unauthorized until the mandatory
holds are closed or the governing plan is formally changed.
