# ADR-0023: Select native SOS support at `1e-7` with a guarded fallback

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-05 |
| Decider | Project owner direction that the historical CPLEX corpus is the gold standard |
| Amends | ADR-0019 native SCIP SOS2 application state and ADR-0021 bounded SCIP SOS residue |

## Context

The current-code 2023-09-22 replay solved all 274 cases to reported optimality,
but the first TP11 dispatch selected an inferior native SOS2 support at SCIP's
`1e-6` primal-feasibility tolerance. Its fixed-HiGHS RMIP objective was
`560071.5387535369`, NI SIR price was `0.11000 NZD/MWh`, SI reference energy
price was `83.48284720 NZD/MWh`, and system cost was `8128.20024663 NZD`.

The CPLEX archive reports NI SIR `0.10350`, SI reference energy `83.48930`, and
system cost `8128.16898`. Solving the case alone, solving the equivalent
explicit interval-binary representation, and an objective-guarded support
challenge all selected the CPLEX state. The defect appeared only after the
canonical 46-case solver history.

Three canonical 47-case prefixes isolated the numerical boundary:

- `1e-6` native SCIP plus an interval-binary support challenge reproduced the
  CPLEX state in 1,181.08 solver-seconds;
- `1e-9` native SCIP reproduced the same state in 907.22 solver-seconds; and
- `1e-7` native SCIP reproduced the same state in 533.58 solver-seconds.

The final `1e-7` prefix completed all 47 primary and pricing solves optimally,
with zero retries. Independent validation passed every case with a maximum
residual of `1.460011679239128e-05`. Relative to the earlier full-day prefix,
only case `211012023091700557` changed. Its pricing objective improved by
`0.031424813671 NZD`; maximum reserve- and node-price changes were
`0.006501786685` and `0.007036277379 NZD/MWh`, respectively.

## Decision

Native SOS2 application cases use SCIP primal feasibility `1e-7`. This equals
the threshold used to classify solved SOS members as active or inactive before
the fixed-RMIP solve. Portable-binary cases retain the qualified `1e-6`
setting and their existing retry semantics.

If native SCIP reports an LP-solver failure at `1e-7`, the same model is
retried at the historically stable `1e-6`. A successful stable fallback is not
accepted blindly: with all ordinary discrete decisions fixed, a class-based
support polisher solves the equivalent explicit interval-binary support MIP at
`1e-9`, fixes that support, and prices it with HiGHS. It replaces the native
fallback only when every support is adjacent and the final fixed-RMIP
objective is strictly better. Failure, non-adjacency, or a tie retains the
native fallback and is recorded in `SosSupportPolishingAudit`.

## Consequences

- SCIP remains the primary MIP solver and HiGHS remains the price-producing
  fixed-RMIP solver.
- The TP11 CPLEX state is selected without a case identifier, price override,
  or CPLEX-specific endpoint convention.
- The ordinary path adds no second MIP and is 54.8% faster than the
  unconditional support-challenge proof on the measured 47-case prefix.
- Historical `1e-6` stability remains available, but its SOS support is
  challenged before fallback prices are accepted.
- Existing immutable evidence keeps its recorded execution fingerprint; new
  replays use this amended tolerance contract.

## Rejected alternatives

- Unconditional interval-binary support solving was rejected because it took
  1,181.08 solver-seconds for 47 cases.
- Unconditional `1e-9` native solving was rejected because it took 907.22
  solver-seconds and has a known SoPlex stability boundary on legacy cases.
- Globally replacing native SOS2 with portable binaries was rejected because
  ADR-0019 records a case where the portable support is inferior.
- A TP11-specific target or price substitution was rejected because it would
  encode the archive result rather than improve the optimization pathway.
- Relaxed SOS convex-envelope discovery was rejected after it produced a
  non-adjacent, therefore SOS2-infeasible, support.

## Verification

- Probity tests distinguish the portable `1e-6` and native `1e-7` contracts,
  prove the guarded native fallback, and bind the support-polishing audit.
- The TP4 CPLEX-gold reserve-kink oracle still passes.
- The hash-bound `1e-7` 47-case manifest and stream reproduce the CPLEX TP11
  quantities and prices at stored precision.

## Revisit triggers

Revisit if a native case needs the stable fallback, if the support challenge
cannot complete, if a new CPLEX difference survives `1e-7`, or if SCIP/Pyomo
changes native SOS2 feasibility semantics.
