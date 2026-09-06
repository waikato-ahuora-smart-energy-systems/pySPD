# Gate 7 — Full reserve formulation and pricing parity

| Field | Value |
|---|---|
| Gate | G7 — Full formulation and pricing equivalent |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Decision | **CLOSED — PASS FOR QUALIFIED MACOS ARM64/GAMS-SCIP/HIGHS PROFILE** |
| Gate 6 dependency | Closed by commit `d9d3969` |
| Implementation | `93d098a` |
| Primary MIP | SCIP through licensed GAMS 54; optimum and incumbent required |
| Pricing RMIP | Fix all 124 discrete decisions, relax every discrete domain, solve with HiGHS 1.15.1 |
| Oracle | Pinned vSPD 5.0.6 semantic Convert matrix/dictionary |
| CPLEX | Deferred by ADR-0008; no CPLEX runtime claim |
| Linux | Deferred by ADR-0011; no Linux claim |

Gate 7 completes the class-composed Pyomo energy/reserve formulation: FIR and
SIR; PLRO, TWRO, and ILRO; generator, group, manual, DC, directional-link, and
HVDC-secondary risks; reserve cover; scarcity tranches; reserve-aware security;
and NMIR sharing, operating zones, control bands, loss curves, and effective
sharing factors.

The canonical anonymous-row comparison is exact over all active Gate 7
algebra in the pinned case: 15,381 columns and 1,403 rows have identical
metadata and matrix hashes. There are no missing, extra, mismatched, or
unmapped terms. The runtime adds a mathematically equivalent portable SOS2
encoding—108 interval binaries and 128 adjacency rows—because the Pyomo GAMS
writer cannot export native `SOSConstraint` components.

The full 56,801-variable/32,254-constraint portable model solves optimally with
SCIP. Its 124 discrete decisions are fixed in a separately rebuilt model, all
discrete domains are relaxed, and HiGHS solves the resulting continuous RMIP.
Primary and pricing objectives differ by only `1.49e-8` NZD. Independent
recomputation passes 1,211 identities with a maximum residual of `8.94e-8`.
All 523 node prices and four island reserve prices are finite. Energy and
reserve finite-difference errors are respectively `1.61e-4` and `3.01e-6`
NZD/MWh.

The focused Gate 7 suite passes 18 tests; the cumulative repository suite
passes 213 tests with one intentional skip. Ruff, mypy, canonical matrix,
solve/price qualification, and the 27-record Probity audit all pass.

See the [source map](source-map.md), [gate checklist](gate-checklist.md),
[matrix evidence](oracle-matrix-parity.json),
[solve/price evidence](solve-price-validation.json), and
[closure decision](closure-decision.md).
