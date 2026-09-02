# ADR-0021: Bound SCIP SOS support residue in portable parity

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-03 |
| Decider | Project owner direction to retain SCIP and continue Gate 12 |
| Amends | ADR-0019 native SCIP SOS2 application state |

## Context

The fresh 2023-01-16 PySPD replay returned two additional positive members in
one native reserve SOS2 set: `2.120995640508827e-7` on `ls1` and
`1.5789907228638119e-6` on `ls8`. The dominant `ls7` member was
`0.999998209`, and all other fixed-state, objective, physics, price,
publication, and report checks passed. The maximum fixed-RMIP objective error
over the eight affected cases was `2.09e-9 NZD`.

SCIP was run with the qualified `1e-6` primal-feasibility tolerance. The GAMS
replay surface records the SOS variable levels after the fixed-state HiGHS
RMIP, where free members can return to zero, while PySPD records the state
captured immediately after SCIP and used to construct that RMIP. Treating the
two tiny structural values as a material support mismatch would therefore
confuse bounded SCIP feasibility residue with a different pricing state.

## Decision

The portable semantic policy accepts a missing or extra
`fixed_sos_members` identity only when its absolute value is no greater than
`2e-6`, twice the qualified SCIP primal-feasibility tolerance. The disposition
is named `scip-sos-feasibility-residue` and remains separate from the ordinary
`1e-8` fixed-state numeric tolerance.

This qualification is permitted only on the fixed SOS-member collection. It
does not apply to discrete variables, objectives, physics, prices,
publications, report values, or other structural differences. Values above the
bound fail closed.

## Consequences

- Native SCIP remains the application MIP solver and HiGHS remains the
  fixed-discrete RMIP solver.
- The rule makes the portable evidence boundary explicit without changing the
  optimization model or widening any economic tolerance.
- Strict CPLEX validation remains deferred and receives no relaxation from
  this decision.
- Future GAMS instrumentation should capture the pre-RMIP inactive-support
  mask directly; that stronger evidence may supersede this bounded rule.

## Rejected alternatives

- Replacing SCIP was rejected by project direction.
- Raising the general fixed-state or sparse-zero tolerance was rejected because
  it would affect unrelated state and physics evidence.
- Treating arbitrary SOS support differences as equivalent was rejected; the
  rule is numeric, member-specific, and fail-closed above `2e-6`.

## Verification

The semantic probity suite proves that a `1.6e-6` structural SOS member is
accepted under the named reason and that `2.1e-6` is rejected. The complete
2023-01-16 semantic result passes 96 surfaces with zero unresolved differences.

## Revisit triggers

Revisit if the SCIP feasibility tolerance changes, if another solver becomes
the portable MIP engine, if residue above `2e-6` is observed, or when the GAMS
pre-RMIP support mask is available.
