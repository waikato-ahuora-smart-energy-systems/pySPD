# 2023-09-22 TP4 reserve-loss breakpoint certificate

## Result

The TP4 mismatch is resolved against the supplied historical CPLEX archive.
The affected case is `211012023091330496` at `22-SEP-2023 01:30`.

SCIP followed by the ordinary fixed-HiGHS RMIP placed the SI FIR backward
post-contingent HVDC flow at `-0.0311611014 MW`, just inside the adjacent loss
segment. Its dominant breakpoint weight was `0.9998547596`. The resulting SI
FIR reserve price was `0.0714403926 NZD/MWh`; the CPLEX archive reports
`0.10000 NZD/MWh` and has reserve received equal to energy sent at the stored
precision, which places it at the zero-flow breakpoint.

Re-solving the fixed RMIP with that already-dominant breakpoint fixed to zero
reproduces the CPLEX observations:

| Observable | Ordinary fixed RMIP | Canonical fixed RMIP | CPLEX archive |
|---|---:|---:|---:|
| SI FIR reserve price (NZD/MWh) | 0.07144039 | 0.10000000 | 0.10000 |
| SI reference energy price (NZD/MWh) | 83.75184848 | 83.77469617 | 83.77470 |
| SI FIR reserve received (MW) | 69.26213238 | 69.23097127 | 69.23097 |
| NI FIR reserve sent (MW) | 68.71334330 | 68.68193508 | 68.68194 |
| SI FIR reserve sent (MW) | 38.72306170 | 38.74799058 | 38.74799 |
| System cost (NZD) | 11826.673287 | 11826.673999 | 11826.67400 |

The pricing objective changes from `555972.9979575574` to
`555972.9972455984 NZD`, a loss of `0.0007119591 NZD`. The implementation
accepts no more than `0.001 NZD`, records the complete decision in
`PricingCanonicalizationAudit`, and retains the unconstrained result whenever
the bound is exceeded.

This is not a zero-flow node-price interval. It is a narrowly bounded
secondary primal solve at a piecewise-linear reserve-loss breakpoint. The
model remains feasible and continuous, and the independent validator checks
the accepted target, objective accounting, and budget.

## Cross-checks

- Official vSPD `v5.0.2` and `v5.0.6` run with SCIP then fixed HiGHS reproduce
  the ordinary `0.07144` result.
- Exact-zero-gap GAMSPy CPLEX on the captured final matrix also returns
  `0.0714403926`; solver choice alone therefore does not reconstruct the
  historical endpoint from the SCIP-generated matrix.
- The 25-case canonical prefix completed with 25 optimal primary and pricing
  solves. TP4 has zero above-precision differences in published energy,
  published reserve, island, and summary results.
- The published SI FIR price changes from `0.07144` to `0.07585`, exactly the
  CPLEX archive value after duration weighting.

## Evidence

- Machine-readable decision:
  [`cplex-tp4-reserve-kink-20230922.json`](cplex-tp4-reserve-kink-20230922.json)
- Prefix benchmark:
  [`cplex-reference-paths-20230922-tp4-reserve-kink.json`](../../../docs/validation/external-evidence.md)
- Mapped CPLEX comparison:
  [`cplex-reference-comparison-20230922-tp4-reserve-kink.json`](cplex-reference-comparison-20230922-tp4-reserve-kink.json)
- Executable regression:
  `tests/gate12/test_cplex_tp4_reserve_kink.py`
