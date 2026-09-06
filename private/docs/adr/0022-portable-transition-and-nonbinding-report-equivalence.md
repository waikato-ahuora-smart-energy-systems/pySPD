# ADR-0022: Portable transition and non-binding report equivalence

## Status

Accepted for the SCIP/HiGHS Gate 12 profile.

## Context

The 2022-11-07 paired replay produced two one-ULP differences in transferred
MW, four different activities on market-node constraints that were strictly
slack with zero shadow price in both solutions, and two risk shadow-price
differences below `0.0001 NZD/MWh`. These values are solver-representation or
alternate-optimum choices. Treating them as exact strings would reject an
economically and physically equivalent SCIP/HiGHS solution.

## Decision

The portable semantic profile compares numeric state-transition quantities at
the existing `1e-8 MW` physics tolerance. State names, identities, event
structure, solve counts, and all other non-numeric transition values remain
exact.

Mapped market-node constraint activity may differ only when both rows have the
same identity, sense, and RHS; both shadow prices are zero at Authority display
precision; and both activities are strictly non-binding on the correct side of
the limit. Binding, infeasible, differently priced, or differently defined rows
continue to fail.

Mapped risk shadow prices use the existing portable `0.0001 NZD/MWh` price
tolerance. This does not relax risk quantities, identities, reserve results, or
any non-price report value.

## Consequences

The exact canonical JSON diagnostic remains unequal and is retained. The
semantic and mapped-report certificates can distinguish harmless solver
choices from changes to feasibility, economics, topology, or control flow.
The policy does not change the Pyomo model, solver settings, or the required
SCIP-MIP to fixed-discrete HiGHS-RMIP pathway.

## Rejected alternatives

- Forcing PySPD onto the GAMS LP basis was rejected because the GAMS basis is
  not an economic requirement and is not portable across solvers.
- Applying a general tolerance to every report quantity was rejected because
  it would obscure material physics and accounting differences.
- Keeping transferred MW byte-exact was rejected because a one-ULP arithmetic
  ordering difference has no physical significance.

## Verification

Probity tests prove that numeric transition residue within `1e-8 MW` passes
while structural transition changes fail; non-binding activity passes only
with common limits and zero duals; binding or priced activity fails; and the
risk-price tolerance is exactly `0.0001 NZD/MWh`. The complete 2022-11-07
mapped report compares 102,571 values with zero failures, and all 72 semantic
surfaces pass with zero unresolved differences.

## Revisit triggers

Revisit if a certified activity is binding in either engine, a risk-price
difference exceeds `0.0001 NZD/MWh`, transition identities or event structure
differ, or a future strict common-solver profile requires basis-level identity.
