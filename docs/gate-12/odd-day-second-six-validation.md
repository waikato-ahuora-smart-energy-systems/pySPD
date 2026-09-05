# Second six odd-day validation record

## Outcome

The second purposeful six-day sample is complete. Ten dynamically assigned
process workers solved 1,045 cases in 207 jobs through SCIP MIP followed by
fixed-discrete HiGHS RMIP. Every counted solve reported optimal, all
independent validations passed, and the largest independently recomputed
residual was `2.89408e-6`, inside the governed `1e-4` tolerance.

The three 2019 days have archived CPLEX output. The complete mapped comparison
checked 2,162,975 values and left zero unresolved above Authority precision.
The 8,158 larger-but-valid differences were admitted only by existing
analytic dual or alternative-allocation certificates.

The three 2022 days have official inputs but no supplied CPLEX result tables.
Their evidence is therefore bounded to exact solver status and independent
model validation, not CPLEX output parity.

| Date | Edge selected | Cases | Jobs | Result |
|---|---|---:|---:|---|
| 2019-06-19 | Highest remaining zero-violation system cost; SOS support stress | 48 | 16 | CPLEX mapped pass |
| 2019-10-16 | Largest remaining daily violation cost | 48 | 16 | CPLEX mapped pass |
| 2019-11-26 | Largest remaining single-period violation | 48 | 16 | CPLEX mapped pass |
| 2022-11-01 | First and largest post-1-Nov consolidated GDX | 322 | 33 | Optimal + independent pass |
| 2022-11-16 | Governed TP42 shortfall-transfer edge | 286 | 96 | Optimal + independent pass |
| 2022-11-24 | Branch-block numerical-recovery edge | 293 | 30 | Optimal + independent pass |

## Corrections exposed

The sample found four generic issues and produced focused regressions:

1. The strict explicit SOS-support oracle can encounter a SoPlex numerical
   failure. It now retries only that failure class at the native-support
   tolerances `1e-7` and `1e-6`; other errors still fail closed.
2. At zero reserve price, the model can leave cleared reserve above the
   governed published requirement without changing objective value. The
   canonicalizer now fixes island reserve and total cleared reserve to that
   requirement, reprices, and accepts the result only inside an explicit
   `1e-7` objective-loss budget. This removed the TP36/37/40 2019-11-26
   quantity mismatches without unit- or date-specific targets.
3. A v5 case label may recur across distinct periods. Parallel jobs are now
   identified and sliced by stable source ordinal, while merged records use
   `(case_id, date_time, trading_period)` identity.
4. A repaired bus price can lie a few tenths of a micro-dollar beyond the
   decimal half-unit boundary. Only this observable receives a `1e-6`
   solver-scale boundary slack; economic and publication tolerances are not
   broadened.

## Pathological date retained outside the pass set

The initially selected 2022-11-17 source exposed one pathological case,
`161302022112200711` (TP24). SCIP did not certify optimality within 900 seconds
using native SOS2, mathematically equivalent portable interval binaries, or a
preceding-period discrete warm start. No feasible incumbent was accepted and
the date is not counted as correctness evidence. Its copied GDX remains in the
repository as a solver-performance regression target.

It was replaced by 2022-11-01, the first day of the Authority's post-1-Nov
daily Pricing GDX regime and the largest file in that archive segment. That
replacement completed all 322 cases.

## Performance

| Date | Preparation | Dynamic execution | Merge | End to end |
|---|---:|---:|---:|---:|
| 2019-06-19 | 20.283 s | 408.569 s | 0.771 s | 429.736 s |
| 2019-10-16 | 21.006 s | 102.168 s | 0.769 s | 124.062 s |
| 2019-11-26 | 21.367 s | 144.333 s | 0.752 s | 166.575 s |
| 2022-11-01 | 156.226 s | 1,653.117 s | 2.661 s | 1,812.865 s |
| 2022-11-16 | 133.186 s | 1,394.701 s | 3.162 s | 1,531.682 s |
| 2022-11-24 | 140.552 s | 934.264 s | 2.386 s | 1,077.875 s |

The machine-readable record is
[`odd-day-second-six-validation.json`](odd-day-second-six-validation.json).
The 12-day corpus is hash-bound by
[`tests/fixtures/odd_day_reference/manifest.json`](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/main/tests/fixtures/odd_day_reference/manifest.json).
