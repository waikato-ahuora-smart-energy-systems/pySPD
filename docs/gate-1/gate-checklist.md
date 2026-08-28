# Gate 1 decision checklist

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Current decision | **IN PROGRESS** |
| Review date | Not scheduled |

| ID | Criterion | Current evidence | State |
|---|---|---|---|
| `G1-01` | Clean fixture reproduction | Class-based runner and one full clean run | Partial |
| `G1-02` | Determinism and basis sensitivity | Two clean runs have identical logical solve/price hashes; basis perturbation open | Partial |
| `G1-03` | All in-scope branches/reports represented | DPS smoke only | **Hold** |
| `G1-04` | Historical packs classified and reproduced | Not recovered | **Hold** |
| `G1-05` | Small repository GDX is smoke-only | Explicitly classified | Met |
| `G1-06` | Semantic matrix export | Not implemented | **Hold** |
| `G1-07` | Preprocessing checkpoints | Not implemented | **Hold** |
| `G1-08` | Per-solve structural/solution snapshots | Status/objective snapshots only | Partial |
| `G1-09` | Approved SPD/AUD overlay | Current executed overlay selects source-default DPS | **Hold** |
| `G1-10` | Exact CPLEX MIP/final-LP price convention | Explicit cross-solver characterization; CPLEX prices unavailable | **Hold** |
| `G1-11` | Comparator mathematics frozen | Objective and price-report structural checks only | Partial |
| `G1-12` | Official secondary comparisons | Not implemented | Open |
| `G1-13` | Calibrated tolerances | Candidate thresholds only | **Hold** |
| `G1-14` | Performance baseline | Initial wall-time observations only | Partial |
| `G1-15` | Independent review and approval | Roles unassigned | **Hold** |

Gate 1 has begun successfully but cannot pass on the repository DPS sample
alone. Stage 2 production formulation work remains unauthorized until the
mandatory holds are closed.
