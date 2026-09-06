# ADR-0008: interim SCIP/HiGHS reference profile

| Field | Value |
|---|---|
| Status | Accepted by project direction |
| Date | 29 August 2026 |
| Decider | Project owner direction recorded in the development task |

> Amended 31 August 2026: optimal SCIP and fixed-state HiGHS statuses are the
> current acceptance boundary. The primary/pricing objective delta remains
> retained evidence, but is not an independent abort condition; native CPLEX
> validation remains deferred.

> Amended 4 September 2026: the supplied historical CPLEX result corpus is the
> gold standard for numerical correctness. SCIP/HiGHS remains the qualified
> execution pathway, but its mapped outputs must be driven toward CPLEX parity.
> Full CPLEX is available through GAMSPy but is not yet integrated into the
> Pyomo fixed-RMIP path; the standalone GAMS Solver Link is demo-size limited.
> Basis-dependent dual residue remains explicit rather than being represented
> as exact parity.

## Context

The pinned vSPD model executes at full size with native GAMS/SCIP, and an
explicit fixed-discrete GAMS/HiGHS RMIP provides finite pricing marginals. Two
clean sample runs produced identical logical solve and price evidence. A native
full-size GAMS/CPLEX Solver Link is not currently available.

Blocking all Gate 1 engineering on CPLEX would prevent progress despite an
executed independent open-solver pathway. Treating any feasible or interrupted
solve as adequate would, however, weaken the reference materially.

## Decision

Use `gams-scip-highs-pricing` as the active adequate vSPD execution and pricing
reference during the current development phase, provided that:

- every primary SCIP MIP reports GAMS solver status `1 Normal Completion` and
  model status `1 Optimal`;
- every fixed-discrete HiGHS RMIP reports the same statuses;
- the primary/pricing objective difference is retained explicitly for later
  cross-validation;
- every expected scenario is present exactly once in the final pricing output;
- every required price is finite; and
- canonical input, matrix, discrete-decision, solution, and report evidence is
  retained with deterministic logical hashes.

Feasible, integer-feasible, locally optimal, time-limited, interrupted, or
otherwise non-optimal statuses do not satisfy this profile.

The repository-local historical CPLEX result corpus is the authoritative
cross-validation oracle. Material mapped differences must be investigated and
corrected where a reproducible compatibility rule exists. The licensed GAMSPy
CPLEX module is a future fixed-RMIP integration path, but it does not itself
guarantee the same basis as the historical vSPD matrix and solve sequence.
Claims of exact historical CPLEX dual reproduction remain prohibited where the
stored dual is basis-dependent and no reproducible rule has been established.

## Consequences

- Gate 1 can progress through GDX, matrix, KKT, price, and corpus evidence now.
- Claims are phrased as pinned-vSPD behavior reproduced with the qualified
  SCIP/HiGHS profile, not CPLEX-identical behavior.
- Solver status checking is a hard acceptance gate, not supporting metadata.
- SCIP uses numerical emphasis with its `1e-6` primal-feasibility tolerance,
  consistent with ADR-0014. Binary values and inactive SOS members are fixed
  before HiGHS repricing; active SOS magnitudes remain continuous.
- CPLEX option discrepancies remain recorded; material result differences are
  no longer deferred merely because native CPLEX execution is unavailable.

## Verification

- Two clean deterministic full-size runs of the repository DPS case.
- Canonical logical hashes for solve records and node prices.
- Independent fixed-LP objective, matrix, KKT, node mapping, and finite-
  difference checks added during Gate 1.
- Re-run the entire qualification corpus before changing this ADR.

## Revisit triggers

- A primary or pricing solve fails to report optimal status.
- SCIP and HiGHS disagree on the fixed solution or pricing objective materially.
- CPLEX becomes available and reveals an economically material difference.
- The supported formulation or GAMS solver links change.
