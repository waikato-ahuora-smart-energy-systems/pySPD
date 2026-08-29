# Gate 4 — core energy-market LP parity

| Field | Value |
|---|---|
| Gate | G4 — Core algebra equivalent |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Current decision | **CLOSED — PASS FOR QUALIFIED MACOS ARM64/HIGHS PROFILE** |
| Gate 3 dependency | Closed by commit `fc5a31a` |
| Python solver | HiGHS 1.15.1 through Pyomo APPSI; optimal required |
| Oracle | Pinned vSPD 5.0.6 Convert/GDX produced by optimal GAMS reference path |
| CPLEX | Deferred by ADR-0008; no CPLEX parity claim |
| Linux | Deferred by ADR-0011; no Linux claim |

Gate 4 delivers a class-composed Pyomo LP vertical slice with immutable normalized
inputs, explicit energy offers and signed demand bids, primary/secondary ramping,
energy scarcity, island balance and violation slacks, vSPD reporting auxiliaries,
objective decomposition, dual normalization, canonical matrix export, and
independent residual and finite-difference price validation.

The approved Stage 4 GAMS projection and Pyomo projection are exactly identical:
882 rows, 11,632 columns, 12,892 nonzeros, and the same logical and structural
SHA-256. All missing/extra/mismatch counters are zero for row bounds, column
bounds, integrality, objective terms, and coefficients. See the
[matrix evidence](oracle-matrix-parity.json).

The representative RTD core solve reports optimal through HiGHS. Independent
recalculation gives a maximum primal residual below `5e-13` MW, no bound or
objective-component breach at the governed tolerances, and dual prices within
`2e-5` NZD/MWh of complete-build load perturbations. See the
[solve and price evidence](solve-price-validation.json).

The focused suite contains 19 Gate 4 tests and the repository suite contains 139
passing tests plus one declared optional-integration skip. The fail-closed Probity
audit validates 24 evidence records across six implementation commits, including
the two Gate 4 implementation commits.

See the [source map](source-map.md), [gate checklist](gate-checklist.md), and
[closure decision](closure-decision.md). Gate 4 is closed and Stage 5 is
authorized for the same qualified profile.
