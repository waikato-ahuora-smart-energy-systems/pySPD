# 2023-01-16 replay certification

The fourth complete paired date passes under the governed portable pathway:
native SCIP solves the MIP, all discrete variables and inactive SOS support are
fixed, and HiGHS solves the resulting RMIP for prices. Pinned GAMS and PySPD
both completed the canonical 109-case prefix; every primary and pricing solve
reported an optimum.

Eight affected intervals occur at 07:30, 07:35, 07:40, and from 08:35 through
08:55. The maximum fixed-RMIP objective difference is `2.09e-9 NZD`. All 96
semantic surfaces pass with zero unresolved differences.

This date exposed four bounded implementation defects, now covered by probity
tests: sparse node-to-bus allocations must default to zero; `FKbandMW` must be
ingested from the offer-parameter surface; SOS activity must use the governed
`1e-7` threshold; and a passive zero-flow transformer tree must inherit the
load-side price from its single lossy boundary. The price normalization is
limited to anchored, zero-dispatch, zero-flow topology; unanchored cycles fail
closed.

One replay returned two candidate-only SOS values below `1.6e-6` around a
dominant `0.999998209` member. [ADR-0021](../adr/0021-bounded-scip-sos-support-residue.md)
classifies these as bounded SCIP feasibility residue, caps the qualification at
`2e-6`, and leaves the ordinary fixed-state tolerance at `1e-8`. This does not
alter the optimization model or its solver path.

The independent zero-flow validator passes all eight cases. It certifies 448
bus observations, 41 node projections across six distinct nodes, and ten TP16
and TP18 publications. The largest certified node-price difference is
`0.25737569005190153 NZD/MWh`; the largest publication difference is
`0.25578 NZD/MWh`. Every node projection has zero residual, and the largest
publication reconstruction residual is `0.00001 NZD/MWh`.

All 13 Authority report tables are implemented. The mapped comparison checks
137,394 values with zero missing or extra identities, zero values above the
governed precision, and zero unimplemented tables. It classifies 1,387 bounded
differences.

The exact JSON diagnostic intentionally remains unequal: 71 surfaces and
2,611,648 leaves differ, predominantly because GAMS and PySPD use different
sparse and report representations. The governed semantic result retains that
diagnostic and resolves every material difference through named tolerances or
hash-bound certificates.

This certifies the complete 2023-01-16 paired comparison and brings the current
v5 total to four passing dates and 17 affected cases. It does not close Gate 12:
exact population enumeration, further representative days, repeat/resume
evidence, the deferred strict CPLEX profile, and the final evidence index remain
open.

The machine-readable evidence index is
[`replay-certification-20230116.json`](replay-certification-20230116.json).
