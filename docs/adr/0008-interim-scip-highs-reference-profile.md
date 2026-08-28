# ADR-0008: interim SCIP/HiGHS reference profile

| Field | Value |
|---|---|
| Status | Accepted by project direction |
| Date | 29 August 2026 |
| Decider | Project owner direction recorded in the development task |

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
- the primary/pricing objective difference is within the governed objective
  tolerance;
- every expected scenario is present exactly once in the final pricing output;
- every required price is finite; and
- canonical input, matrix, discrete-decision, solution, and report evidence is
  retained with deterministic logical hashes.

Feasible, integer-feasible, locally optimal, time-limited, interrupted, or
otherwise non-optimal statuses do not satisfy this profile.

Native CPLEX validation is deferred cross-validation. It is no longer a
prerequisite for continuing Gate 1 or later implementation work under this
interim profile. A CPLEX comparison remains required before making any future
claim specifically about CPLEX parity or historical CPLEX dual reproduction.

## Consequences

- Gate 1 can progress through GDX, matrix, KKT, price, and corpus evidence now.
- Claims are phrased as pinned-vSPD behavior reproduced with the qualified
  SCIP/HiGHS profile, not CPLEX-identical behavior.
- Solver status checking is a hard acceptance gate, not supporting metadata.
- CPLEX option discrepancies remain recorded but are deferred rather than
  blocking current development.

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
