# ADR-0025: Retry only numerical LP failures in the explicit SOS support oracle

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-05 |
| Decider | Project owner direction that CPLEX is the gold standard |
| Amends | ADR-0023 strict native SOS support with guarded fallback |

## Context

The 2019-06-19 TP5 support challenge failed in SoPlex at the oracle's strict
`1e-9` feasibility tolerance. Retaining the baseline state left a non-adjacent
reserve-loss SOS support and a 13.543 MW CPLEX quantity mismatch.

## Decision

The explicit support oracle first solves at `1e-9`. Only an error identified as
an LP-solver failure is retried at `1e-7` and then `1e-6`. Any other failure,
or failure after the final attempt, is re-raised. The selected support must
still be adjacent, fixed, repriced by HiGHS, independently validated, and
strictly objective-improving before it can replace the native support.

## Consequences

TP5 completes with a maximum independent residual below `1e-9`, and the full
2019-06-19 day passes all 718,270 mapped CPLEX values. The fallback does not
turn nonoptimal states or arbitrary solver failures into accepted evidence.

## Rejected alternatives

Accepting the invalid relaxed support, globally weakening feasibility, and
case-specific support selection were rejected.

## Verification

A probity test forces the `1e-9` LP failure and proves the ordered retry. The
full-day hash-bound result is recorded in the second odd-day validation pack.

## Revisit triggers

Revisit if the retry changes a valid strict result, admits non-adjacent support,
or a future SCIP/SoPlex release changes the failure classification.
