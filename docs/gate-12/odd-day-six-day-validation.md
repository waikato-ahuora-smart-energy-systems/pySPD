# Six odd-day dynamic validation record

## Outcome

Six purposefully unusual days now form a hash-bound in-repository corpus. Ten
process workers dynamically executed 449 small jobs containing 1,058 canonical
cases. Every SCIP MIP and fixed-discrete HiGHS RMIP solve reported optimal, no
case retry was needed, and every independent model validation passed. The
largest independent residual was `1.48012e-6`, within the governed `1e-4`
validation tolerance.

For the three 2019 dates, complete archived CPLEX output was available. The
mapped comparator checked 2,174,167 values and left zero values unresolved
above Authority publication precision. It accepted 7,451 larger differences
only through existing analytic-price or alternative-allocation certificates;
it did not hide them with a widened scalar tolerance.

The three 2022 sources have no supplied archived CPLEX result tables. Their
evidence is therefore bounded to full-stream PySPD optimality plus independent
validation, not CPLEX output parity. Existing Gate 12 historical GAMS evidence
separately records 282/282 exact optimal selected cases on 2022-11-25 and
274/274 on 2022-12-04 under the qualified residue-recovery profile.

## Selection

| Date | Reason | Cases |
|---|---|---:|
| 2019-04-07 | NZ DST fall-back; 50 trading periods | 50 |
| 2019-09-29 | NZ DST spring-forward; 46 trading periods | 46 |
| 2019-10-21 | Largest archived 2019 violation event found: 11.8 MW and NZD 10.03m | 48 |
| 2022-11-09 | Twelve shortfall-transfer candidates, the largest 2022 governed count | 294 |
| 2022-11-25 | Five shortfall-transfer candidates plus residual recovery | 315 |
| 2022-12-04 | Known residual-recovery edge | 305 |

The public consolidated 2022 Pricing GDX inventory begins in November, so the
2022 DST transition dates were not available from that source.

## Dynamic execution

The class-based `DynamicCaseJobPlanner` creates canonical contiguous jobs.
`ProcessShardCoordinator` keeps at most ten jobs in flight and submits the next
job whenever a process becomes idle. Every process owns its model and solver
instances. Completed artifacts are restored to source order before the merged
record hash is calculated. A failed job cancels pending work and prevents a
partial result from being presented as a complete day.

The smaller v3 inputs used one case per job. The much larger v5 inputs used
three cases per job to amortize repeated GDX loading while retaining 98–105
jobs per day for load balancing.

A final real-process smoke exercised the completed bounded dispatcher itself:
ten one-case jobs on ten workers completed in 34.115 seconds, with all solves
optimal, independent validation passed, and merged record hash
`a4ddec843910b15a70945ca34bb4fe5b9018ddc981e9652886d9138bcfc62859`.

| Date | Jobs | Preparation | Dynamic execution | Merge | End to end |
|---|---:|---:|---:|---:|---:|
| 2019-04-07 | 50 | 22.244 s | 357.798 s | 0.970 s | 381.143 s |
| 2019-09-29 | 46 | 21.350 s | 109.769 s | 0.802 s | 132.045 s |
| 2019-10-21 | 48 | 21.821 s | 99.428 s | 0.827 s | 122.200 s |
| 2022-11-09 | 98 | 145.379 s | 1,353.650 s | 2.933 s | 1,502.703 s |
| 2022-11-25 | 105 | 151.202 s | 1,403.602 s | 2.817 s | 1,558.378 s |
| 2022-12-04 | 102 | 148.445 s | 1,506.983 s | 2.837 s | 1,659.019 s |

The complete machine-readable record, including source, benchmark, record, and
comparison hashes, is
[`odd-day-six-day-validation.json`](odd-day-six-day-validation.json). The
immutable inputs and CPLEX results are governed by
[`tests/fixtures/odd_day_reference/manifest-v1.json`](../../tests/fixtures/odd_day_reference/manifest-v1.json).

## Corrections found by the corpus

The deliberately unusual inputs exposed three generic defects:

1. The legacy v3 converter omitted `i_IsPriceResponse` and `i_PotentialMW`.
   Both are now carried into the canonical offer parameters.
2. A v5 market-reserve factor could survive for an offer absent from the exact
   reserve-variable domain. The Pyomo sum now applies the same offer-domain
   guard as vSPD before dereferencing the variable.
3. A decimal value exactly at half an Authority display unit could be rendered
   a few binary-float ulps beyond the boundary. The comparator now applies only
   `1e-12` rendering slack; substantive tolerances and certificate rules are
   unchanged.

Each defect has a focused regression in addition to the corpus and full-suite
checks.
