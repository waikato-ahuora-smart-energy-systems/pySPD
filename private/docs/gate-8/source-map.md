# Gate 8 source and behavior map

| Concern | Pinned vSPD source | PySPD owner | Verification |
|---|---|---|---|
| Case/TP/publication selection | `vSPDperiod.gms`, input mappings | `DailyCaseSelector` | source-order, filters, zero-duration tests |
| Compatibility and preparation | `vSPDsolve.gms` sections 5–7 | `DailyCasePreparer`, `DailyCase` | study-mode contract and pinned GDX qualification |
| Overrides | `vSPDoverrides.gms` sections 1–11 | `OverrideApplier` | every family, scope precedence, before/after audit |
| Prior dispatch fallback | `vSPDsolve.gms:923` | `DailyRunner` | two-case accepted-generation test |
| Shortfall eligibility/removal | `vSPDsolve.gms:1306-1334` | `ShortfallLoop` | eligible, ineligible, margin, scaling-disable tests |
| Transfer target walk | `vSPDsolve.gms:1346-1405` | Gate 3 `ShortfallTransferResolver` composed by `ShortfallLoop` | transfer and untransferred regression tests |
| Loop bound | `maxSolveLoops`, shortfall guard | `ShortfallLoop` | no fourth solve or unsolved mutation at a limit of three |
| SCIP/fixed-RMIP solve | `pyspd_fixed_lp_solve.inc` | `ReserveCaseExecutor`, Gate 7 solve policy | 124 fixed decisions; SCIP/HiGHS optimal objectives |
| Bus repair/disconnection | `vSPDsolve.gms:1449-1506` | `MarketPricePostProcessor` | invalid/SOS, adjacent repair, dead/disconnected tests |
| Node allocation/transfer | `vSPDsolve.gms:1511-1554` | `MarketPricePostProcessor` | allocation-weighted and dead-node transfer tests |
| Publication | `vSPDsolve.gms:1820-1844` | `PublishedPriceAggregator` | seconds weighting, zero duration, rounding, independent validator |
| Resume safety | no direct GAMS equivalent | `DailyRunCheckpoint`, `DailyRunner` | prefix and environment/formulation fingerprint rejection |

The production path remains modular: immutable contracts in `types.py`, data
selection/preparation in `selection.py`, override policy in `overrides.py`,
solve-loop composition in `solver.py`, price services in `pricing.py`, the
daily state machine in `runner.py`, and an independent publication validator in
`validation.py`.
