# WPT1101 zero-flow price diagnosis

## Outcome

The fixed-RMIP/node-price difference for case `61012022110425024` is resolved
in the pricing engine. It was not caused by dispatch, matrix coefficients,
HiGHS version, feasibility tolerances, node allocation, or publication logic.
It was the choice of subgradient at two zero-flow AC-loss kinks.

The corrected target-case replay gives:

| Surface | GAMS | corrected PySPD | absolute difference |
| --- | ---: | ---: | ---: |
| raw bus 816 | 17.572622712126556 | 17.572622712126545 | 1.1e-14 |
| raw bus 820 | 17.552852079426955 | 17.552852079426938 | 1.8e-14 |
| node WPT1101 | 17.572622712126556 | 17.572622712126545 | 1.1e-14 |
| fixed-RMIP objective | -2177.951866644149 | -2177.9518666441813 | 3.2e-11 |

WPT1101 has allocation factor 1.0 to bus 816, so its corrected node price is
the corrected bus-816 price without another transformation.

## Root cause

Bus 816 is a passive leaf connected to bus 521 by `ORO_WPT1.1`. Bus 820 is a
passive leaf connected to bus 532 by `STK_T7.L7`. Both branches have zero net
and directed flow in the accepted fixed RMIP and use piecewise-linear losses.
At zero flow, the LP has two valid directional derivatives:

- incremental export from the leaf, selected by the unnormalised HighsPy
  basis; and
- incremental load at the leaf, selected by pinned GAMS/HiGHS at the two WPT
  branches and required by the project's nodal-price convention.

The parent-bus prices already agreed to approximately `6e-14 NZD/MWh`. For a
passive receiving leaf, receiving-end loss share `r`, and first loss-segment
factor `f`, the canonical `+load` sensitivity is

`leaf_price = parent_price * (1 + (1-r)f) / (1-rf)`.

Pinned vSPD uses `r = 1`. The exact checks are therefore:

- bus 816: `17.56748390070199 / (1 - 0.00029243280919125)` =
  `17.572622712126556`;
- bus 820: `17.548241222731384 / (1 - 0.000262684188)` =
  `17.552852079426952`.

The second result differs from the stored GAMS double by only `3.6e-15`.

## Correction and scope

`NetworkPricingEngine` now detects electrically connected, passive,
zero-flow AC-loss leaves and replaces the basis-dependent dual with the exact
one-sided `+1 MW load` sensitivity. It handles either declared branch
orientation by selecting the loss factor for inward flow. Buses with load,
offers, or bids are excluded, as are disconnected buses and non-loss branches.

The subsequent full-prefix replay establishes an important qualification:
pinned GAMS/HiGHS does not choose the load-side derivative consistently at all
otherwise comparable zero-flow leaves. The general PySPD rule is consistent
with its stated sensitivity convention, but it changes 51 final-case repaired
bus marginals relative to GAMS's selected basis. Only one reaches a reported
node (`KIN1009`). This is now an explicit certification boundary rather than
being hidden by a WPT-specific branch allow-list.

The AC direction and loss-segment domains also preserve vSPD's explicit
`forward`, then `backward` semantic order. This improves matrix comparability;
the price correction itself does not depend on solver column order.

Probity coverage is in
`tests/network/test_ac_network.py::test_zero_flow_loss_branch_uses_gams_load_subgradient`
for both declared branch orientations. The complete test suite passes.

## Refreshed evidence boundary

The full 196-case prefix has now been regenerated through both PySPD and the
pinned GAMS SCIP-MIP → fixed-discrete → HiGHS-RMIP path. The direct WPT bus and
node values pass, but the rolling `TP35` WPT1101 publication differs by
`0.00515 NZD/MWh` (`0.03907%`) because the generalized convention also applies
through preceding publication state. The independent source-topology
certificate reconstructs that publication as `13.18718 NZD/MWh`, exactly the
PySPD result, from all six weighted TP35 cases. Numerical price parity is
therefore certified under the documented convention; report completeness
remains open.

See the hash-bound
[`post-wpt-rerun-certification-20221106.json`](post-wpt-rerun-certification-20221106.json)
and its
[`human-readable summary`](post-wpt-rerun-certification-20221106.md).
