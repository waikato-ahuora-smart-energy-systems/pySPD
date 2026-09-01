# ADR-0018: Apply the portable price tolerance to published report rows

| Field | Decision |
|---|---|
| Status | Accepted by project direction for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-02 |
| Decider | Project owner direction that SCIP/HiGHS is the adequate current solve pathway, with CPLEX validation deferred |
| Amends | ADR-0017 mapped report-row comparison policy |

## Context

The first post-ADR-0017 paired date, 2023-01-17, passes primary physics,
fixed-RMIP objective, fixed-discrete state, reserve prices, case selection,
publication weights, and state transition. The independent topology validator
also proves all 49 material zero-flow bus-price alternatives, their three node
projections, and the three material rolling energy-price differences.

The complete report comparator exposes a separate bounded representation
effect: 165 ordinary published energy rows differ by at most `0.00002
NZD/MWh`, and one published SIR row differs by `0.00001 NZD/MWh`. These rows
are computed from portable-solver marginals that already pass the semantic
price policy, but five-decimal Authority display precision alone is narrower
than that solver claim.

## Decision

Version the mapped-row comparator as
`authority-pyspd-mapped-report-row-parity-zero-flow-certified-v4` and apply a
`0.0001 NZD/MWh` tolerance to published energy, FIR, and SIR price rows. This
is the same price tolerance used by the semantic and independent zero-flow
validators, and is stricter than the `0.001 NZD/MWh` portable tolerance
retained for raw branch endpoint and marginal prices.

All identities remain exact. Independently certified material zero-flow
differences remain bound to their named certificate. A published price beyond
`0.0001 NZD/MWh`, a missing or extra row, or any non-price difference outside
its existing rule fails closed. Version-3 artifacts remain readable and
immutable but are not reinterpreted under version 4.

## Consequences

- Portable report equivalence remains distinct from strict solver identity.
- Strict CPLEX evidence receives no relaxation from this decision.
- Probity tests require both energy and reserve rows within the bound to pass
  and rows outside the bound to fail.
