# Current-code full-day replay: 2023-09-22

## Outcome

The final uninterrupted current-code replay completed all 274 cases through
SCIP MIP -> fixed-discrete -> HiGHS RMIP. Every MIP and fixed RMIP reported an
optimal solution and no case retried. Native SOS2 cases used the corrected
`1e-7` SCIP feasibility contract; no stable-tolerance fallback was required.
Solver time was 3,385.26 seconds and wall time was 4,082.10 seconds. This is
10.6% and 9.8% slower than the immediately preceding `1e-6` replay, but it
removes the TP11 optimization-state error and sharply improves validation.

The first attempt exposed a multiple-boundary passive-tree case at 23:15 whose
HiGHS basis scalar lay 0.000029116 below its non-empty analytical intersection.
The corrected rule preserves any scalar inside the interval and projects only
an outlier to its nearest analytical endpoint. A synthetic red/green unit test
and an isolated real-case replay cover the correction. The restarted full day
then passed the formerly blocking case in sequence.

## CPLEX comparison

The governed comparison covers 3,964,727 values. Before applying the TP24
equal-cost allocation certificate it reports 10,010 certified and 28,472
above-precision differences. The certificate moves exactly its fourteen
source-proven identities, producing 10,024 certified and 28,458
above-precision differences. No unrelated count changes.

All published-energy rows now pass:

- zero published-energy rows remain above Authority precision;
- 535 non-exact published-energy rows are independently covered by their
  analytical dual intervals; and
- the only unresolved publications are the two documented TP1 historical
  reserve-price residues.

The comparison remains fail-closed. In particular, the 26,758 `NodeResults_TP`
differences are the previously documented partial daily-node surface rather
than a claim of full report parity.

## Validation boundary

The benchmark records `independent_validation_passed: false`. Twelve cases are
above its absolute `1e-4` threshold: eleven objective-reconstruction residuals
and one NI SIR reserve-flow residual of `0.000142022 MW`. The maximum residual
is a `0.0333622 NZD` objective-reconstruction difference, down 90.7% from
`0.360361 NZD`; failed cases fell from 165 to 12. This is retained verbatim and
accepted only under the project direction that an optimal SCIP/HiGHS solve is
adequate for the present evidence boundary. It is not relabelled as an
independent-validator pass.

Evidence:

- [`cplex-reference-paths-20230922-current-v3-full-day.json`](cplex-reference-paths-20230922-current-v3-full-day.json)
- [`cplex-reference-comparison-20230922-current-v3-full-day.json`](cplex-reference-comparison-20230922-current-v3-full-day.json)
- [`cplex-reference-comparison-20230922-current-v3-full-day-tp24-certified.json`](cplex-reference-comparison-20230922-current-v3-full-day-tp24-certified.json)
- [`cplex-tp24-energy-allocation-20230922-current-v3-full-day.json`](cplex-tp24-energy-allocation-20230922-current-v3-full-day.json)

## Subsequent TP11 resolution

The first TP11 case had used an inferior native SOS2 support at SCIP feasibility
`1e-6`; it was not a reserve-loss breakpoint or a valid dual interval. Native
SCIP at `1e-7` improves the fixed-RMIP objective by `0.031424813671 NZD` and
reproduces CPLEX's NI SIR price, SI reference price, reserve sharing, system
cost, and system OFV at stored precision. The full-day result confirms the
correction persists in canonical sequence. See the
[`TP11 native-support certificate`](cplex-tp11-native-support-20230922.md).
