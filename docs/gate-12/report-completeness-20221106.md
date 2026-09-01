# 2022-11-06 complete report and semantic certification

The canonical 196-case PySPD prefix was rerun after completing the class-based
projectors for every pinned-vSPD report table and correcting published rows to
use the trading-period DateTime. The model's governed optimization structure is
unchanged: reporting reads registered solution handles, input definitions, and
duals without changing optimization rows.

Both previously unimplemented tables now pass for all four affected cases.

| Table | Compared values | Missing | Extra | Above Authority precision | Maximum absolute error |
| --- | ---: | ---: | ---: | ---: | ---: |
| `RiskResults_TP` | 171 | 0 | 0 | 0 | 0.0000493181 |
| `SummaryResults_TP` | 60 | 0 | 0 | 0 | 0.000003528 |

The final mapped-row comparison passes across 13 Authority tables and 68,558
values. It has zero missing or extra identities, zero values above the governed
portable-profile comparator, and zero unimplemented tables. All 142 Authority
fields map for every case; candidate-only audit and diagnostic fields are
explicitly governed supplements.

The 257 classified values are fail-closed exceptions with bounded rules: the
independent source-topology certificate governs zero-flow price identities;
branch endpoint prices use the approved `0.001 NZD/MWh` portable raw-price
tolerance; and offer-level FIR/SIR alternatives are accepted only with the same
identities, nonnegative values, and aggregate equality within the accumulated
Authority row-rounding budget. Deliberately unequal aggregates fail probity
tests.

The hash-bound mapped-row result is consumed by the semantic validator. All
twelve canonical surfaces pass for all four affected cases, with zero failed
surfaces and zero unresolved differences. This certifies the complete
2022-11-06 comparison under the SCIP-MIP → fixed-discrete → HiGHS-RMIP portable
profile. Gate 12 itself remains open for the remaining population,
representative-day, repeat/resume, and other checklist obligations.

The machine-readable evidence index is
[`report-completeness-20221106.json`](report-completeness-20221106.json).
