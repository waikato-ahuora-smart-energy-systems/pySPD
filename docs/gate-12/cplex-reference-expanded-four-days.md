# Expanded CPLEX reference analysis — four additional days

## Outcome

Four further days were selected by the governed SHA-256 ranking, copied
byte-for-byte into the immutable CPLEX corpus, and replayed through SCIP MIP →
fixed-discrete → HiGHS RMIP. All 667 cases completed and every primary and
pricing solve reported optimal. The results are complete, but they are not all
row-exact against the CPLEX gold standard.

The two 2019 days reproduce every CPLEX summary value at its stored precision.
Their remaining discrepancies are concentrated in non-unique continuous
allocation and dual surfaces. The two 2023 days expose unresolved result
differences, including published energy prices and, on 2023-11-24, a material
system objective difference. Solver success alone therefore remains a
necessary but insufficient correctness condition.

| Day | Cases | Solve calls | Solver seconds | Wall seconds | CPLEX values | Above precision | Maximum difference |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019-05-16 | 48 | 48 | 890.901 | 968.947 | 719,231 | 2,876 | 117.91461 |
| 2019-06-06 | 48 | 48 | 835.094 | 913.633 | 721,167 | 2,493 | 131.456812 |
| 2023-09-22 | 274 | 274 | 3,401.380 | 4,110.802 | 3,964,736 | 34,438 | 77.296935 |
| 2023-11-24 | 297 | 300 | 3,646.039 | 4,430.761 | 4,286,432 | 38,724 | 700,000 |

The three additional solve calls on 2023-11-24 are governed reserve-shortfall
loop resolves, not failed solves. The independent absolute diagnostic remains
deliberately stricter than the accepted solver-status boundary and fails all
four days. Its maxima are 0.000126743, 0.000110199, 0.321633, and 2.347531,
respectively; the last three maxima are fixed-discrete pricing-objective
residuals. These remain visible diagnostics and are not represented as CPLEX
parity.

## CPLEX comparison findings

### 2019-05-16 and 2019-06-06

Both days have zero missing or extra identities and zero above-precision
summary results. Maximum summary differences are only 4.929e-6 and 4.766e-6.
The largest primal differences are alternative dispatch allocations:

- 2019-05-16 has a maximum node-generation difference of 0.779032 MW;
- 2019-06-06 has a maximum node-generation difference of 5.218 MW; and
- offer reserve differences are certified where the total allocation on the
  same flat face is equivalent.

Large market-node-constraint price maxima (117.91461 and 131.456812 NZD/MWh)
are non-unique constraint-dual allocations. They do not change the matched
summary objective. The 2019 archive has no published-price tables.

### 2023-09-22

All 274 cases solve optimally. There are 162 missing and 279 extra risk-result
identities caused by a different risk-setter representation; all other mapped
tables are identity-complete. The largest summary difference is 0.003499 NZD
in system cost (0.000316% of CPLEX). The largest published-energy difference
is 0.50780 NZD/MWh at ORO1101 TP29, or 0.507145% of the CPLEX value.

The maximum 77.296935 result is a repaired raw-bus price at an unallocated bus,
not a published node price. Nevertheless, the published-energy difference is
outside the analytic zero-flow explanation described below and remains an
unresolved output-parity failure.

### 2023-11-24

All 297 cases solve optimally and every mapped identity is present. The maximum
700,000 result is a non-unique market-node-constraint dual and is not a primal
or published-price difference. Material unresolved differences remain:

- the largest published-energy difference is 2.51039 NZD/MWh at ARG1101 TP29,
  1.367912% of the CPLEX value;
- case `231012023111835784` has PySPD system cost 40,488.450903 NZD versus
  CPLEX 40,440.25323 NZD, a 48.197673 NZD or 0.119182% difference; and
- the same case has a system-OFV difference of 5,644.752787, or 0.005711% of
  the CPLEX system OFV.

That case reports no material generation, reserve, branch, ramp, or
market-node violation in either summary. Its fixed-RMIP objective differs from
the SCIP MIP objective by only 0.187588, so the 5,644.75 CPLEX difference
cannot be dismissed as the normal SCIP-to-HiGHS pricing residual. This is an
open formulation/result-parity finding.

## Zero-flow price boundary

The expanded ten-day analytic scan covers 1,731 cases and 217,680 passive
zero-flow observations. Of 93,075 distinguishable endpoint choices, CPLEX
selects export 76,443 times (82.13%) and load 16,632 times. Of the load choices,
16,376 (98.46%) occur at buses with no node allocation. Only 256 case-node
observations propagate to BPT1101, KIN1009, RFN1102, or WPT1101.

For the four new days, the maximum publication changes predicted solely by
replacing a CPLEX load endpoint with PySPD's governed export endpoint are
0.023038 NZD/MWh on 2023-09-22 and 0.030708 NZD/MWh on 2023-11-24. Those bounds
are far below the observed 0.50780 and 2.51039 maxima. The analytic interval
correctly certifies genuine zero-flow degeneracy, but it does not explain or
waive the new published-price failures.

See
[`cplex-zero-flow-analysis-ten-days.json`](cplex-zero-flow-analysis-ten-days.json)
and
[`cplex-zero-flow-analysis-ten-days.md`](cplex-zero-flow-analysis-ten-days.md).

## Solver-policy correction

SCIP's SoPlex LP failed after presolve on two legacy cases even though their
original matrices are solvable. The class-based solve state machine now
retries only an explicit SCIP `LP solver` failure with
`presolving/maxrounds=0`. It preserves the model, feasibility tolerance,
zero MIP gap, single thread, and warm-start policy. Other solver errors are
re-raised. Probity tests cover both activation and fail-closed behaviour.

## Evidence

Compact run summaries bind the ignored full JSONL streams by SHA-256:

- [`cplex-reference-paths-20190516-highs.json`](cplex-reference-paths-20190516-highs.json)
  and [`cplex-reference-comparison-20190516-highs.json`](cplex-reference-comparison-20190516-highs.json)
- [`cplex-reference-paths-20190606-highs.json`](cplex-reference-paths-20190606-highs.json)
  and [`cplex-reference-comparison-20190606-highs.json`](cplex-reference-comparison-20190606-highs.json)
- [`cplex-reference-paths-20230922-highs.json`](cplex-reference-paths-20230922-highs.json)
  and [`cplex-reference-comparison-20230922-highs.json`](cplex-reference-comparison-20230922-highs.json)
- [`cplex-reference-paths-20231124-highs.json`](cplex-reference-paths-20231124-highs.json)
  and [`cplex-reference-comparison-20231124-highs.json`](cplex-reference-comparison-20231124-highs.json)

The comparison summaries now retain the identity, observable, CPLEX value,
candidate value, tolerance, and absolute error for each table's maximum. This
makes a maximum auditable even when the first bounded failure examples occur
in earlier cases.
