# Gate 1 decision checklist

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Current decision | **HOLD — NOT CLOSED** |
| Review date | Not scheduled |

| ID | Criterion | Current evidence | State |
|---|---|---|---|
| `G1-01` | Clean fixture reproduction | Class-based runner and one full clean run | Partial |
| `G1-02` | Determinism and basis sensitivity | Two clean runs have identical solve, price, canonical GDX, dictionary, solution, and matrix logical hashes; basis perturbation open | Partial |
| `G1-03` | All in-scope branches/reports represented | DPS smoke only | **Hold** |
| `G1-04` | Historical packs classified and reproduced | Not recovered | **Hold** |
| `G1-05` | Small repository GDX is smoke-only | Explicitly classified | Met |
| `G1-06` | Semantic matrix export | GAMS Convert DumpGDX/DictMap export; 33,131 rows, 58,232 columns, and 111,925 nonzeros canonicalized reproducibly | Met for sample; corpus expansion open |
| `G1-07` | Preprocessing checkpoints | Not implemented | **Hold** |
| `G1-08` | Per-solve structural/solution snapshots | All solve statuses/objectives plus final-scenario fixed-LP solution, matrix, and name dictionary | Partial: per-scenario matrix snapshots open |
| `G1-09` | Approved SPD/AUD overlay | Current executed overlay selects source-default DPS | **Hold** |
| `G1-10` | Approved MIP/final-LP price convention | Explicit SCIP MIP to fixed-discrete HiGHS RMIP accepted by ADR-0008; independent final-scenario price and LP checks pass; CPLEX deferred | Met for sample; finite-difference/corpus evidence open |
| `G1-11` | Comparator mathematics frozen | Exact canonical hashes; objective tolerance; independent activity/bound/stationarity and node-price equations implemented | Partial: calibration approval open |
| `G1-12` | Official secondary comparisons | Not implemented | Open |
| `G1-13` | Calibrated tolerances | Candidate thresholds only | **Hold** |
| `G1-14` | Performance baseline | Initial wall-time observations only | Partial |
| `G1-15` | Independent review and approval | Roles unassigned | **Hold** |

Gate 1 has begun successfully but cannot pass on the repository DPS sample
alone. The [closure decision](closure-decision.md) records the material
blockers. Stage 2 production work remains unauthorized until the mandatory
holds are closed or the governing plan is formally changed.
