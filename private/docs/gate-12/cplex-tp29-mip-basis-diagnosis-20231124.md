# 2023-11-24 TP29 CPLEX price diagnosis

The largest published-energy difference on the expanded 2023-11-24 day is
ARG1101 in TP29: CPLEX reports 183.51990 NZD/MWh and SCIP → HiGHS reports
181.00951 NZD/MWh. The absolute difference is 2.51039 NZD/MWh, or 1.3679% of
the CPLEX value.

This is not a primal-model or LP-tolerance mismatch. The exact vSPD v5.0.6
matrix was exported before the MIP and after the SCIP fixed-RMIP state was
applied. It was then rebuilt as a GAMSPy model and solved with CPLEX under the
installed GAMSPy academic licence.

| Replay for case `241012023110125942` | Objective | ARG1101 price |
|---|---:|---:|
| Archived vSPD CPLEX | 90,150,365.90023 | 175.221 (displayed) |
| SCIP MIP → HiGHS fixed-RMIP | 90,150,365.9002257 | 172.3515734605 |
| Fresh CPLEX solve of SCIP's fixed LP | 90,150,365.9002257 | 172.35157346048533 |
| CPLEX MIP → fixed CPLEX RMIP continuation | 90,150,365.9002257 | 175.221050811755 |

The CPLEX and SCIP paths select the same 16 binary bounds and the same active
support among 118 SOS2 members. A mechanical comparison found zero fixed-state
bound differences. A fresh CPLEX solve of that fixed algebra selects the same
marginal as HiGHS to 1.5×10⁻¹¹ NZD/MWh. Only the CPLEX MIP-to-RMIP continuation,
which carries CPLEX's solve state into the pricing solve, selects the archived
price. This isolates the discrepancy to a non-unique LP dual/basis selected by
solver history.

Consequences:

- the SCIP → HiGHS result remains an optimal and independently validated price
  vector for the same fixed LP;
- exact reproduction of this historical CPLEX marginal requires the CPLEX MIP
  continuation, not merely replacing HiGHS with a fresh CPLEX fixed-LP solve;
- a solver-independent parity rule should certify the CPLEX price as belonging
  to the valid dual set rather than treating one degenerate basis as unique;
- the repository now includes `tools.replay_fixed_matrix`, a GAMSPy-based
  canonical-matrix oracle that can reproduce both replay experiments without
  asking a GAMSPy licence to execute the original GAMS source.

Machine-readable evidence is in
[`cplex-tp29-mip-basis-diagnosis-20231124.json`](cplex-tp29-mip-basis-diagnosis-20231124.json).
