# Gate 11 closure decision

## Decision

Gate 11 is **closed — pass at the amended engineering-formulation boundary**.
The separately selected `spd-v16.0-reserve` profile is authorized for continued
engineering and Gate 12 validation on the documented macOS arm64,
SCIP-MIP/fixed-discrete-HiGHS-RMIP pathway.

This decision is machine-recorded under the project direction that no separate
independent validation reviewer or human approval is required.

## Passing basis

- authoritative formulation, readable feature source, and representative 2026
  GDX inputs are versioned and hash-bound;
- the 23 June 2026 boundary and required 44-symbol schema fail closed;
- v16 behavior is implemented through separate immutable data, preprocessing,
  `ModelComponent`, `Formulation`, pricing, result, reporting, and executor
  classes;
- equal-price tie-break, paired battery mode, reserve-risk/requirement,
  reserve-price fallback, economics, bad-price, and reporting deltas have
  focused red/green tests;
- the oracle overlay now snapshots, fixes, restores, and exports the v16 battery
  discrete variable before the HiGHS RMIP;
- a representative RTD case reaches optimal primary and pricing solves in both
  implementations, with canonical oracle matrix and independent node-price
  validation passing; and
- the complete regression suite passes without changing the v5 structural
  fingerprint.

## Explicit limitations and Gate 12 transfer

Gate 11 does not assert exact parity. The representative Pyomo and Authority
feature-oracle objectives differ by approximately `7.8328185`, and reserve
prices differ. Gate 12 must resolve or formally classify those differences and
prove strict raw-to-report parity. Gate 12 also owns CPLEX, full PRSS solve and
performance, an NRSS orchestration profile if brought into scope, complete-day
and complete-corpus evidence, and the previously registered v5 parity debt.

Linux x86_64 CI remains skipped by project direction. Gate 0 licence and
redistribution decisions remain pending, so public distribution is held.

