# 2022-11-07 replay certification

The fifth complete paired date passes under the governed portable pathway:
native SCIP solves the MIP, all discrete variables and inactive SOS support are
fixed, and HiGHS solves the resulting RMIP for prices. Pinned GAMS and PySPD
both completed the canonical 210-case prefix; every primary and pricing solve
reported an optimum.

Six affected cases occur from 19:00 through 19:25. The maximum fixed-RMIP
objective difference is `5.61e-10 NZD`. All 72 semantic surfaces pass with zero
unresolved differences.

This date exposed a report-only scarcity reconstruction defect. A mapped target
node began with zero load and received `1.2136 MW` during the shortfall-transfer
re-solve. PySPD had discarded the dynamic scarcity factor and price while its
initial limit was zero, under-reporting `SystemOFV` by `22,755.841253843 NZD`.
Preprocessing now retains dynamic factors and prices for zero-load nodes,
distinguishes fixed scarcity-limit overrides, and recomputes dynamic limits
only for positive final load. The corrected PySPD value is
`97,663,886.484739274 NZD` versus GAMS `97,663,886.48474 NZD`.

The independent zero-flow validator passes all six cases. It certifies 348 bus
observations, 22 node projections across four distinct nodes, and seven
publications. The largest certified node-price difference is
`0.21193442971684817 NZD/MWh`; the largest publication difference is
`0.2775699999999972 NZD/MWh`. Node and publication reconstruction residuals
are zero.

All 13 Authority report tables are implemented. The mapped comparison checks
102,571 values with zero missing or extra identities, zero values above the
governed precision, and zero unimplemented tables. It classifies 793 bounded
differences. Four market-node LHS differences are certified only because the
constraints are strictly non-binding and zero-priced in both engines. Two risk
dual differences below `0.0001 NZD/MWh` and two one-ULP transfer quantities are
governed by [ADR-0022](../adr/0022-portable-transition-and-nonbinding-report-equivalence.md).

The exact JSON diagnostic intentionally remains unequal: 51 surfaces and
1,961,711 leaves differ, predominantly because GAMS and PySPD use different
sparse and report representations. The governed semantic result retains that
diagnostic and resolves every material difference through named tolerances or
hash-bound certificates.

This certifies the complete 2022-11-07 paired comparison and brings the current
v5 total to five passing dates and 23 affected cases. It does not close Gate 12:
exact population enumeration, further representative days, repeat/resume
evidence, the deferred strict CPLEX profile, and the final evidence index remain
open.

The machine-readable evidence index is
[`replay-certification-20221107.json`](replay-certification-20221107.json).
