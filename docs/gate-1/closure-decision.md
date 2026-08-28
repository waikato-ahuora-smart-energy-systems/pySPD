# Gate 1 closure decision

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Decision date | 29 August 2026 |
| Decision | **HOLD — NOT CLOSED** |
| Active reference | Optimal SCIP MIP → fixed-discrete HiGHS RMIP under ADR-0008 |
| CPLEX | Deferred cross-validation; not a current blocker |

## Decision

Gate 1 is not closed. The executed DPS case proves that the active reference
profile, canonical GDX and matrix exports, independent LP checks, and
independent node-price mapping work for that case. It does not meet the
governing plan's Gate 1 breadth, checkpoint, comparator, and review criteria.

Starting Stage 2 production work would therefore bypass an explicit dependency
in the governing stage-and-gate plan. Gate 2 remains not started. Read-only
research or Gate 1 evidence work may continue, but production data contracts,
package APIs, and model foundations must wait for a Gate 1 pass or a formally
recorded change to the governing plan.

## Material blockers

| ID | Blocker | Required closure evidence |
|---|---|---|
| `G1-B01` | Only the source-default DPS path has executed evidence; in-scope SPD/AUD modes, branches, solve paths, and report families are not covered | Reviewed fail-closed SPD/AUD overlay plus reproducible fixtures and required snapshots for every in-scope path |
| `G1-B02` | The 2023/2025 and historical packs are not fully classified and reproduced | Per-pack hashes, applicable formulation/data profiles, execution results or an explicit provenance-only/deferred classification |
| `G1-B03` | Material preprocessing boundaries do not have oracle checkpoints or an observational-neutrality proof | Governed instrumentation, pristine/instrumented comparison, and checkpoint manifests |
| `G1-B04` | Structural/solution evidence is not retained before and after every solve and re-solve | Per-solve model variant, matrix, bounds/fixings, discrete/SOS state, primal, marginal, status, and post-solve snapshots |
| `G1-B05` | Incremental comparator mappings and complete KKT definitions are not frozen | Versioned mapping/sign/scale/ranged-row/complementarity specification with analytic tests |
| `G1-B06` | Official secondary comparisons and corpus-wide tolerance calibration are incomplete | Reproducible official comparisons, discrepancy classifications, empirical distributions, and approved thresholds |
| `G1-B07` | Independent validation ownership and approval are absent | Named independent reviewer and recorded Gate 1 approval |

## Evidence that is complete for the current sample

- two clean runs with identical logical solve, report, input, solution, matrix,
  and dictionary hashes;
- 15 optimal SCIP primary MIPs and 15 optimal HiGHS fixed-discrete RMIPs;
- one deterministic GAMS Convert matrix/name-dictionary export;
- independent activity, row/column bound, and stationarity validation; and
- exact native node-price reconstruction for the nine nodes in the final
  scenario snapshot, with report-precision agreement.

## Reconsideration rule

Reconsider closure only after every blocker above is linked to immutable
evidence and the Gate 1 checklist has no mandatory hold or unexplained oracle
self-inconsistency. CPLEX evidence is required only if the proposed claim is
expanded to CPLEX-specific parity.
