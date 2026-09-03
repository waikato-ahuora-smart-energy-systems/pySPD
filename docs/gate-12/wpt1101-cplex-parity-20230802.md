# WPT1101 CPLEX parity correction — 2023-08-02

## Decision

The supplied historical CPLEX vSPD result is the gold standard. PySPD therefore
uses the CPLEX-compatible export-side marginal at passive zero-flow AC-loss
leaves. The earlier solver-independent `+1 MW load` normalization is superseded
for qualified production pricing; its immutable GAMS evidence remains useful
as a diagnosis of dual degeneracy.

## Root cause

In all six TP36 cases, `WPT1101` maps with allocation 1.0 to bus 817. Bus 817 is
a passive leaf behind `ORO_WPT1.1`; branch flow, directed flow, dynamic loss,
fixed loss, WPT load and WPT generation are all zero. The source GDX gives a
first loss-segment factor of `0.00031989028183125`.

At this piecewise-linear kink the fixed RMIP has more than one valid optimal
dual. With parent price `p` and first loss factor `f`, historical CPLEX selected
the export endpoint `p * (1 - f)`. PySPD formerly selected the incremental-load
endpoint `p / (1 - f)`. Positive parent prices make the former lower.

## Rerun result

The six cases were rerun through SCIP MIP → fixed-discrete → HiGHS RMIP after
the correction. Every solve reported optimal.

| Surface | CPLEX | corrected PySPD | absolute difference |
|---|---:|---:|---:|
| TP36 arithmetic base-node WPT1101 | 773.0625333333334 | 773.0625328434725 | 4.90e-7 NZD/MWh |
| TP36 duration-weighted published WPT1101 | 776.12518 | 776.1251883043195 | 8.30e-6 NZD/MWh |

The published difference fell from `0.49679648` to `0.00000830 NZD/MWh` and is
`1.07e-6%` of the CPLEX price. The residual is consistent with upstream parent
price differences below the precision of the stored CPLEX case CSVs.

The rerun covered case IDs `21012023080530595`, `21012023080535598`,
`21012023080540599`, `21012023080545600`, `21012023080550601`, and
`21012023080555602`. Its full JSONL SHA-256 is
`168ae4e647044b925a1c0b0fc4dcb5263659eda61eb2b0021ab90fa071a4286e`.

## Scope boundary

This correction eliminates the worst published-energy discrepancy. It does
not establish exact parity for every CPLEX dual: complete-day analysis shows
that CPLEX sometimes selected the other endpoint on other degenerate zero-flow
faces. Exact replication of every basis-dependent dual requires the historical
CPLEX matrix order, options and basis sequence. Full CPLEX is licensed through
GAMSPy, but a fixed-Pyomo-matrix GAMSPy backend and basis-equivalence evidence
remain to be implemented. Physical results and prices away from those
degenerate faces are unaffected by this correction.
