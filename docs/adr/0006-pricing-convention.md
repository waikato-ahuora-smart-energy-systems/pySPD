# ADR-0006: pricing convention

| Field | Value |
|---|---|
| Status | Proposed; interim execution convention accepted by ADR-0008 |
| Date | 28 August 2026 |
| Deciders | Optimization lead, market SME, validation lead |

## Context

Energy and reserve prices depend on constraint marginals, sign conventions,
units, duration, discrete decisions, solver options, and post-processing. A MIP
does not provide economically meaningful duals in the same way as an LP. The
pinned source options do not by themselves prove whether the qualified runtime
performs a final fixed-discrete LP or which marginals reports consume.

Assuming current CPLEX `solvefinal` defaults or copying a common fixed-MIP recipe
could reproduce neither the historical runtime nor published vSPD behavior.

## Decision

Gate 1 must pin exact runtime versions and all effective options. Under
ADR-0008, the active characterization runtime is SCIP MIP followed by an
explicit fixed-discrete HiGHS RMIP; CPLEX characterization is deferred. Gate 1
must demonstrate:

- whether a final continuous model is solved after each relevant MIP;
- the transformation from primary MIP to pricing problem;
- treatment of every integer, semi-discrete, and SOS structure;
- which primary/final primals and marginals feed each report;
- dual signs, reduced costs, units, duration, scaling, and ranged rows; and
- basis/degeneracy sensitivity.

Only after that decision does `Vspd506PricingEngine` implement the convention.
If it is fixed-MIP pricing, PySPD:

1. retains an immutable primary solution;
2. fixes every accepted discrete decision;
3. applies only approved domain/SOS transformations;
4. proves the pricing model is continuous;
5. fingerprints the matrix difference;
6. extracts duals from the pricing LP only; and
7. uses primary primals for physical reports and pricing-LP duals for prices.

LP prices require accepted optimal termination, canonical signs/units, and
finite-difference validation. Price-bearing ranged rows are mapped explicitly.

## Consequences

- MIP pricing implementation waits until Gate 1 evidence exists.
- Primary and pricing snapshots must be stored separately.
- Strict historical prices may require a pinned solver method/basis profile.
- Stage 7 repeats the complete pricing audit after NMIR/reserve binaries arrive.

## Rejected alternatives

- **Read “MIP duals”:** not a valid market-pricing convention.
- **Assume `solvefinal=1`:** not proven by the pinned source/runtime yet.
- **Use final-LP primals as dispatch automatically:** may overwrite the accepted
  physical solution.
- **Use one global dual-sign rule:** unsafe across row transformations.

## Verification

- Gate 1 oracle runtime/effective-option evidence and matrix snapshots.
- Analytic sign/unit/complementarity/reduced-cost cases.
- Finite-difference demand and reserve perturbations.
- Gate 6 submodel and Gate 7 full-formulation pricing-model audits.
- Exact PySPD-to-pinned-vSPD published-output comparison at reference precision.

## Revisit triggers

- Gate 1 proves a different convention than the fixed-MIP candidate.
- Solver/runtime upgrades alter final-LP or basis behavior.
- A new formulation changes price-bearing equations or post-processing.
