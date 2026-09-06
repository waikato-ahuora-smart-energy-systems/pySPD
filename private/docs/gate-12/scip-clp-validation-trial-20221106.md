# SCIP to CLP fixed-RMIP validation trial — 2022-11-06

## Status

**Experimental validation profile implemented; not a qualified replacement for
the portable SCIP-to-HiGHS profile.**

The class-based profile `scip-mip-fixed-clp-rmip` retains native SCIP for the
primary MIP and substitutes CLP only for the continuous fixed-RMIP pricing
solve. The qualified default remains `scip-mip-fixed-highs-rmip`.

## Hash-bound case

- Input: `Pricing_20221106.gdx`
- Source SHA-256:
  `282ac2abeaa2f0c7c6e26b967e2ba90289c0ba5a9e696b99069d11350d3037b8`
- Case: `61012022110425024`, `06-NOV-2022 17:25`
- Target node: `WPT1101`
- Runtime: Pyomo 6.10.1, PySCIPOpt 5.7.1, HiGHS 1.15.1, CyLP 0.94.0

Both SCIP primary solves and both fixed-RMIP solves reported optimal, and the
fixed-discrete maps were exactly equal. The independent reserve/HVDC validator
passed all 1,203 residual checks; its maximum residual was `2.69e-8`.

| Observable | SCIP → HiGHS | SCIP → CLP | Absolute difference |
|---|---:|---:|---:|
| Fixed-RMIP objective (NZD) | -2177.951866644093 | -2177.951866617130 | 2.6963e-8 |
| WPT1101 node price (NZD/MWh) | 17.572622712126567 | 17.572622712126570 | 3.55e-15 |
| Maximum repaired node-price difference (NZD/MWh) | — | — | 2.84e-14 |
| Maximum raw bus-dual difference (NZD/MWh) | — | — | 500000.0 |

The large raw-dual difference occurs on a degenerate zero-flow LP face. The
existing independent load-side topology reconstruction normalizes that
solver-basis choice, yielding materially identical node prices. Consequently,
CLP is useful as an independent objective, primal, and reconstructed-price
validator, but raw bus duals must not be claimed as strict solver-independent
observables.

## Performance trial

The first end-to-end single-case executions took 15.549 seconds with HiGHS and
16.048 seconds with CLP. This cold result includes SCIP, model construction,
and CLP's first import/startup cost.

Five repeated solves of the already fixed historical RMIP produced:

| Solver | Median fixed-RMIP time | Runs (seconds) |
|---|---:|---|
| HiGHS | 2.3383 s | 2.3309, 2.3383, 2.3479, 2.3374, 2.4572 |
| CLP | 1.4941 s | 2.3074, 1.4904, 1.4941, 1.4841, 1.4953 |

After first-use startup, CLP reduced median fixed-RMIP time by approximately
36.1%. This is a one-case macOS-arm64 trial, not a whole-day performance claim.

## Acceptance boundary

Before CLP can become a qualified alternative, run the complete paired-date
corpus and require optimal status, fixed-state equality, objective and primal
parity, independent price reconstruction, report parity, and an explicit
classification for every raw-dual difference. The trial does not alter any
existing Gate 12 certificate.
