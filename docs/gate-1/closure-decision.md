# Gate 1 closure decision

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Decision date | 29 August 2026 |
| Decision | **HOLD — NOT CLOSED** |
| Active reference | Optimal SCIP MIP → fixed-discrete HiGHS RMIP under ADR-0008 |
| CPLEX | Deferred cross-validation; not a current blocker |

## Decision

Gate 1 is not closed. The executed DPS plus nine-case SPD corpus and one AUD run
prove the active reference profile, fail-closed overlays, standard/audit report
families, canonical GDX/matrix exports, independent LP checks, dead-node price
transfer, and independent node-price mapping across all in-scope 2025-pack
RTD/PRSS inputs. The 2023 pack is hash-bound and validly deferred. The result
still does not meet the governing plan's separate population, checkpoint,
per-solve-snapshot, and complete incremental-comparator criteria.

Starting Stage 2 production work would therefore bypass an explicit dependency
in the governing stage-and-gate plan. Gate 2 remains not started. Read-only
research or Gate 1 evidence work may continue, but production data contracts,
package APIs, and model foundations must wait for a Gate 1 pass or a formally
recorded change to the governing plan.

## Material blockers

| ID | Blocker | Required closure evidence |
|---|---|---|
| `G1-B01` | The required 546 affected RTD intervals, matched controls, daylight-saving cases, and remaining preprocessing/fallback/re-solve feature cells are not populated | Reproducible fixtures and required snapshots for every remaining in-scope path |
| `G1-B03` | Material preprocessing boundaries do not have oracle checkpoints or an observational-neutrality proof | Governed instrumentation, pristine/instrumented comparison, and checkpoint manifests |
| `G1-B04` | Structural/solution evidence is not retained before and after every solve and re-solve | Per-solve model variant, matrix, bounds/fixings, discrete/SOS state, primal, marginal, status, and post-solve snapshots |
| `G1-B05` | Current full-matrix activity/bound/stationarity checks are frozen, but incremental feature projection, split-row/dual transforms, and complementarity mappings are incomplete | Versioned mapping/sign/ranged-row/complementarity specification with analytic tests |

## Evidence that is complete for the executed samples

- two clean runs with identical logical solve, report, input, solution, matrix,
  and dictionary hashes;
- 38 optimal SCIP primary MIPs and 38 optimal HiGHS fixed-discrete RMIPs in the
  frozen RTD/PRSS/AUD corpus;
- ten deterministic GAMS Convert matrix/name-dictionary exports;
- independent activity, row/column bound, and raw/scale-normalized stationarity
  validation; and
- exact native node-price reconstruction for the nine nodes in the final
  DPS scenario snapshot, with report-precision agreement;
- hash-bound, fail-closed SPD and AUD configuration overlays;
- 13 normal reports and the AUD family of six CSVs plus `AllData.gdx`; and
- exact native reconstruction of all 20,344 frozen-corpus prices, including 38
  dead-node price transfers, with five-decimal report-precision agreement;
- exact recovery/classification hashes for the named 2023 and 2025 Authority
  packs; and
- keyed official comparisons for every in-scope 2025-pack RTD/PRSS case, with
  CPLEX differences retained as secondary solver-profile divergences.

## Reconsideration rule

Reconsider closure only after every blocker above is linked to immutable
evidence and the Gate 1 checklist has no mandatory hold or unexplained oracle
self-inconsistency. ADR-0009 confirms that independent review is not required.
CPLEX evidence is required only if the proposed claim is expanded to
CPLEX-specific parity.
