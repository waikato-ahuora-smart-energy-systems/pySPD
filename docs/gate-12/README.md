# Gate 12 — End-to-end parity validation

| Field | Value |
|---|---|
| Gate | G12 — E2E parity validated |
| Status | **PLANNED — MANDATORY PARITY DEBT REGISTERED** |
| Applicable baselines | vSPD v5.0.6 at `21b1cf33…`; SPD v16 feature source at `84ed3c9…` |
| Entry | After Gate 10 for v5.0.6; after applicable Gate 11 work for a new formulation |
| Package manager | `uv` only |
| Strict profile | Historical pinned-vSPD compatibility solver/profile |
| Portable profile | GAMS-SCIP primary MIP → fix all discrete → HiGHS RMIP |
| Human approval | No separate independent reviewer required under project direction |

Gate 12 owns the exact end-to-end validation intentionally removed from the
amended Gate 8 boundary. It does not reopen or duplicate the Stage 8
implementation. It proves the complete observable chain from immutable raw GDX
through selection, preprocessing, overrides, every solve and re-solve, accepted
physics, fixed-discrete pricing, price repair, publication, and reports.

## Inherited parity debt

| Obligation | Gate 8 evidence | Gate 12 completion condition |
|---|---|---|
| Affected interval identities | 427 immutable dead-node cases over the 139 hash-bound dates | Exactly 546 unique case IDs, leaving zero unidentified intervals |
| Shortfall behavior | Exact affected fixture plus bounded analytic state-machine coverage | All 546 cases replayed against pinned GAMS and PySPD |
| Whole-day behavior | Representative single case | Complete representative normal, feature-rich, outage, 46-period, and 50-period days |
| Official energy prices | Identity set exact; max difference `1.23576` NZD/MWh | Strict-profile parity or case-specific degeneracy certificate |
| Official reserve prices | Identity set exact; max difference `0.0746` NZD/MWh | Strict-profile parity or case-specific degeneracy certificate |
| Reports | Stage 8 price/publication surfaces | Every Gate 9 in-scope report and field compared end to end |
| Repeat/resume | Analytic checkpoint contract | Repeated and resumed whole-day equality |

## Gate 11 v16 parity debt

| Obligation | Gate 11 evidence | Gate 12 completion condition |
|---|---|---|
| Representative RTD objective | Pyomo exceeds feature oracle by approximately `7.8328185` | Explain and eliminate the algebraic difference, or reject the compatibility claim |
| Reserve prices | Both pathways are optimal but published reserve prices differ | Strict comparison plus finite-difference/basis classification |
| PRSS | Schema and eight-interval selection characterized | Full solve, performance, prices, and reports |
| NRSS | Schema characterized; orchestration unsupported | Add and qualify an explicit profile if included in the declared scope |
| CPLEX | Deferred by project direction | Execute the strict profile before a CPLEX-based claim |
| Formulation/source safeguard | PDF battery ambiguity rule differs from demonstrable feature-source behavior | Record the governing decision and compare its observable effect |

## Required evidence pack

- `interval-identity-manifest.json`: exactly 546 identities, each bound to one
  of the 139 Gate 1 source hashes and a discovery rationale;
- per-interval state-transition comparisons for pinned GAMS and PySPD;
- full-day manifests for ordinary, defect, feature-rich, and daylight-saving
  dates;
- primary/pricing structural fingerprints and accepted solution hashes;
- raw, repaired, node, reserve, weighted, rounded, and report-field diffs;
- common-optimal-face, finite-difference, KKT, and basis evidence for any
  claimed solver-sensitive price;
- deterministic repeat and checkpoint/resume comparisons;
- strict-profile and portable-profile result summaries kept separate; and
- a discrepancy register with zero unresolved material entries at closure.

## Fail-closed rules

- A date list is not an interval-identity manifest.
- A relaxed solve cannot enumerate the population because Gate 1 observed a
  false negative.
- An objective match does not prove price or report parity.
- A portable-profile solver difference cannot be labeled strict compatibility.
- Missing identities, stale solve state, incomplete full days, or unexplained
  material prices hold Gate 12.
- Gate 8 closure cannot be used as substitute evidence for any Gate 12 item.

The authoritative work and pass criteria are in
[`Stage 12 — End-to-end parity validation`](../pyomo-vspd-stage-gate-plan.md#stage-12--end-to-end-parity-validation).
