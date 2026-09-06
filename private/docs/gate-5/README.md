# Gate 5 — AC network, losses, and security parity

| Field | Value |
|---|---|
| Gate | G5 — AC and security equivalent |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Current decision | **CLOSED — PASS FOR QUALIFIED MACOS ARM64/HIGHS PROFILE** |
| Gate 4 dependency | Closed by commit `8adc359` |
| Implementation | `ed150d3` |
| Probity evidence | `21cfc61` |
| Python solver | HiGHS 1.15.1 through Pyomo APPSI; optimal required |
| Oracle | Pinned vSPD 5.0.6 semantic Convert matrix/dictionary |
| CPLEX | Deferred by ADR-0008; no CPLEX parity claim |
| Linux | Deferred by ADR-0011; no Linux claim |

Gate 5 replaces the Gate 4 island balance with a class-composed bus-level DC
network. It includes immutable topology and security data, reference angles,
directional AC flows and capacities, fixed and piecewise-linear losses, bus
balance and slacks, LE/GE/EQ branch and market-node security constraints,
nodal pricing, branch rentals, dead-node classification, and an independent
network validator.

The pinned GAMS and Pyomo Stage 5 projections are exactly identical after the
declared `1e-12` canonical serialization rule: 29,825 rows, 30,084 columns,
73,953 nonzeros, and matching logical and structural SHA-256 values. Every
missing, extra, bound, integrality, objective, and coefficient discrepancy
counter is zero. See the [matrix evidence](oracle-matrix-parity.json).

The representative 923-bus, 1,044-AC-branch case solves optimally. All 29,825
independently recomputed flow, balance, loss, capacity, and security checks pass;
the maximum residual is below `1.1e-10` against the `1e-7` threshold. Its
finite-difference nodal-price error is below `5.2e-5` NZD/MWh. See the
[solve and price evidence](solve-price-validation.json).

The focused suite contains 32 tests covering two- and three-bus networks,
congestion, reverse flow, disconnected/dead topology, fixed/PWL loss boundaries,
both flow directions, all security senses and slack directions, market-node bid
factors, rentals, and independent finite-difference pricing. Probity binds every
Gate 5 production path to the prior behavioral red test.

See the [source map](source-map.md), [gate checklist](gate-checklist.md), and
[closure decision](closure-decision.md). Gate 5 is closed and Gate 6 is
authorized for the same qualified profile.
