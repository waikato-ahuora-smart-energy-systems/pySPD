# ADR-0026: Canonicalize zero-price reserve surplus within an objective guard

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-05 |
| Decider | Project owner direction that CPLEX is the gold standard |
| Extends | ADR-0024 validated solver-kink price intervals |

## Context

On 2019-11-26 TP36, TP37, and TP40, SCIP/HiGHS and CPLEX reported optimal but
PySPD retained zero-priced cleared FIR above the governed published reserve
requirement. The objective cannot select among those free quantities. CPLEX
selects cleared reserve equal to the requirement.

## Decision

When the island-reserve dual is zero and island or cleared reserve exceeds the
independently recomputed published requirement by more than `1e-6 MW`, add a
secondary equality fixing both island reserve and total cleared reserve to the
requirement. Reprice with HiGHS and accept only when objective loss is at most
`1e-7 NZD`. Candidate and accepted targets are recorded in the existing
canonicalization audit.

## Consequences

The rule is driven by model quantities and prices, not CPLEX values, offer
names, case IDs, or dates. The 2019-11-26 full day passes all 721,264 mapped
CPLEX values after the change.

## Rejected alternatives

Publishing arbitrary surplus, selecting a named marginal offer, and embedding
CPLEX reference quantities were rejected.

## Verification

Focused tests cover zero/nonzero reserve-price candidate selection and the
audit residual. Full-day CPLEX comparison and independent validation pass.

## Revisit triggers

Revisit if a zero-price equality causes objective loss above budget, becomes
infeasible, or conflicts with a future published-requirement definition.
