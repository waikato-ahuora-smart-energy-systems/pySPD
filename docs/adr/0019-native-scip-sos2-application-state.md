# ADR-0019: Use native SOS2 state in the SCIP application solve

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-02 |
| Decider | Project owner direction to continue Gate 12 under the adequate SCIP/HiGHS pathway |
| Amends | ADR-0008 interim SCIP/HiGHS reference profile |

## Context

The portable adjacent-interval binary representation of the HVDC reserve-loss
curve selected the interval immediately below the GAMS/SCIP SOS2 interval for
case `181012023010315527` on 2023-01-18. The primary objectives were nearly
equal, but fixing the different interval for the HiGHS RMIP changed the pricing
objective by about `0.001508 NZD` and materially changed FIR sharing.

An isolated Pyomo model using a native SOS2 constraint reproduced the GAMS/SCIP
support exactly: SI FIR used `ls8` weight `0.6437732783974608` and `ls9` weight
`0.3562267216025392`. Its pricing objective was
`-35707.222094924015 NZD`, versus `-35707.22209492485 NZD` from GAMS.

## Decision

The v5 application executor replaces the case's configured HVDC SOS
representation with `SosRepresentation.NATIVE` before assembly. SCIP solves
the MIP with the native SOS2 set. The established pricing path then captures
and fixes the inactive SOS support and all discrete variables, deactivates the
SOS component, and solves the continuous RMIP with HiGHS.

This changes the solver representation used to select discrete/SOS state. It
does not change the economic objective, breakpoints, loss algebra, reserve
algebra, or report definitions. The execution fingerprint continues to bind
the exact source and environment.

## Consequences

- The application path matches the SOS state selected by pinned GAMS/SCIP on
  the diagnosed historical interval.
- HiGHS still receives an ordinary fixed-state RMIP; it is not required to
  solve an active SOS model.
- Portable interval binaries remain available as an explicit formulation
  option for tests and other backends, but no longer govern the v5 application
  solve.
- Earlier immutable replay certificates describe their recorded execution
  fingerprints. Regression replay under this representation is tracked
  separately.

## Rejected alternatives

- Retaining the adjacent-interval binaries was rejected because it preserved a
  real fixed-state pricing mismatch.
- Forcing the observed `ls8`/`ls9` weights was rejected because weights must be
  optimized; only inactive support and discrete state are fixed for pricing.
- Relaxing the fixed-RMIP objective tolerance was rejected because the native
  formulation removes the mismatch.

## Verification

- Probity test `test_application_solve_uses_native_scip_sos_state` fixes the
  application boundary.
- The isolated historical case reproduces native GAMS SOS support and pricing
  objective.
- The complete 190-case 2023-01-18 PySPD prefix solved optimally on its first
  attempt; all four affected fixed-RMIP objectives match GAMS within
  `8.23e-10 NZD`.

## Revisit triggers

Revisit if SCIP or Pyomo changes native SOS semantics, if a supported solver
cannot preserve/fix the selected support, or when the deferred strict CPLEX
profile is executed.
