# 2023-01-18 replay certification

The third complete paired date passes under the governed SCIP/HiGHS pathway.
Pinned GAMS completed the canonical 190-case prefix, and PySPD repeated it with
native SCIP SOS2 state followed by fixed-discrete HiGHS RMIP pricing. All
primary and pricing solves reported an optimum.

Four affected intervals occur from 16:10 through 16:25. The native SOS2 change
is a solver-representation correction: it aligns PySPD's selected reserve-loss
support with GAMS without changing the objective or economic algebra. Across
the four cases, the largest fixed-RMIP objective difference is
`8.23e-10 NZD`.

All twelve semantic surfaces pass with zero unresolved differences. The
independent zero-flow load-derivative validator certifies 190 bus observations,
seven node projections, and the two material TP33 publications. The publication
differences are `0.01345 NZD/MWh` at `OTA2202` and `0.07510 NZD/MWh` at
`WPT1101`; both reconstruct with zero residual from the certified bus-price
convention.

All 13 Authority report tables are implemented. The mapped-row comparison
checks 68,516 values with zero missing or extra identities, zero values above
governed precision, and zero unimplemented tables. It classifies 401 bounded
differences. Two are a solver-dependent allocation of the same
`152.41571 NZD/MWh` dual total between simultaneously binding SFD22 market-node
limits, governed by [ADR-0020](../adr/0020-binding-market-node-dual-allocation.md).

This certifies the complete 2023-01-18 paired comparison. It does not close
Gate 12: exact population enumeration, further representative dates,
repeat/resume evidence, the deferred strict CPLEX profile, current-profile
regression of earlier certified dates, and the final evidence index remain
open.

The machine-readable evidence index is
[`replay-certification-20230118.json`](replay-certification-20230118.json).
