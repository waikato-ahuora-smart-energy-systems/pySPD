# Expanded CPLEX reference analysis — four additional days

## Outcome

Four further days were selected by the governed SHA-256 ranking, copied
byte-for-byte into the immutable CPLEX corpus, and replayed through SCIP MIP →
fixed-discrete → HiGHS RMIP. All 667 cases completed and every primary and
pricing solve reported optimal. The results are complete, but they are not all
row-exact against the CPLEX gold standard.

The two 2019 days reproduce every CPLEX summary value at its stored precision.
Their remaining discrepancies are concentrated in non-unique continuous
allocation and dual surfaces. The two 2023 days expose published-energy
differences. The initially observed 2023-11-24 system-objective difference has
since been corrected by matching vSPD's daily shortfall-transfer guard. Solver
success alone therefore remains a necessary but insufficient correctness
condition.

| Day | Cases | Solve calls | Solver seconds | Wall seconds | CPLEX values | Above precision | Maximum difference |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019-05-16 | 48 | 48 | 890.901 | 968.947 | 719,231 | 2,876 | 117.91461 |
| 2019-06-06 | 48 | 48 | 835.094 | 913.633 | 721,167 | 2,493 | 131.456812 |
| 2023-09-22 | 274 | 274 | 3,401.380 | 4,110.802 | 3,964,736 | 34,438 | 77.296935 |
| 2023-11-24 | 297 | 297 | 3,646.039¹ | 4,430.761¹ | 4,286,432 | 38,430 | 700,000 |

¹ The complete-day timing is retained from the original run; targeted record
replacement corrects results and solve-call accounting but does not claim a
remeasured complete-day duration.

The original three additional solve calls on 2023-11-24 were daily RTD
shortfall-transfer resolves that vSPD suppresses; the corrected three-case
rerun uses one solve per case. The independent absolute diagnostic remains
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
in system cost (0.000316% of CPLEX). Before the passive-tree correction, the
largest published-energy difference was 0.50780 NZD/MWh at ORO1101 TP29, or
0.507145% of the CPLEX value.

The maximum 77.296935 result is a repaired raw-bus price at an unallocated bus,
not a published node price. The ORO1101 defect was a passive zero-injection
tree `509 → 518 → 522` containing two consecutive lossy zero-flow branches.
The original normalization handled a leaf behind one lossy boundary, including
lossless transformer descendants, but stopped at passive bus 518 because it
was incident to both lossy branches. The generalized implementation orients
only an acyclic passive component with exactly one live boundary and propagates
the selected export endpoint through every edge. Components with cycles or
multiple live boundaries remain solver-selected.

The progressive replay now covers all 274 cases and 48 trading periods.
Forty-seven periods have no unresolved published-energy difference. TP12's
former 0.06490 NZD/MWh ATU1101 scalar residual is certified by intersecting
the analytical intervals imposed by its two live zero-flow boundaries; the
HiGHS scalar is retained. TP1's two ARI rows are likewise certified by the
intersection at the shared root of a passive transformer tree with two
parallel live boundaries. The current TP1/TP12-substituted complete stream has
29,631 unresolved and 10,044 certified mapped differences. Published energy
has 167 unresolved rows, all in TP4. See the
[`progressive validation record`](cplex-reference-passive-tree-progress-20230922.md).

### 2023-11-24

All 297 cases solve optimally and every mapped identity is present. The maximum
700,000 result is a non-unique market-node-constraint dual and is not a primal
or published-price difference. The material published-price difference remains:

- the largest published-energy difference is 2.51039 NZD/MWh at ARG1101 TP29,
  1.367912% of the CPLEX value.

The three affected TP16 cases now match CPLEX summary, offer, island, bus and
branch values at displayed precision. The maximum summary difference is
4.892×10⁻⁶ and the solve count falls from six to three. The TP16 published
ABY0111 price is exact at the stored precision: 158.78761 NZD/MWh in both
PySPD and CPLEX. The defects were:

- PySPD applied shortfall transfer in daily RTD mode despite the vSPD guard;
- summary reporting omitted `ENERGYSCARCITYNODE` from deficit generation;
- PySPD did not retain vSPD's pre-shortfall `busDisconnected` state for an
  electrical island with no generation; and
- bus reporting projected a successfully transferred dead-node price back to
  its disconnected bus, whereas vSPD does that only for nodes still marked
  dead after the transfer search.

Canonical-matrix replay separately proves that the TP29 ARG1101 result is a
non-unique dual selected by solve history. Fresh CPLEX on SCIP's fixed LP
reproduces HiGHS, while CPLEX MIP followed by its fixed-LP continuation
reproduces the archived CPLEX price at report precision, with identical
objective and fixed binary/SOS bounds. See
[`cplex-tp29-mip-basis-diagnosis-20231124.md`](cplex-tp29-mip-basis-diagnosis-20231124.md).

## Zero-flow price boundary

The expanded ten-day analytic scan covers 1,731 cases and 217,680 passive
zero-flow observations. Of 93,075 distinguishable endpoint choices, CPLEX
selects export 76,443 times (82.13%) and load 16,632 times. Of the load choices,
16,376 (98.46%) occur at buses with no node allocation. Only 256 case-node
observations propagate to BPT1101, KIN1009, RFN1102, or WPT1101.

The original single-boundary scan predicted maximum publication changes of
0.023038 NZD/MWh on 2023-09-22 and 0.030708 NZD/MWh on 2023-11-24. Its first
bound did not include a chain with consecutive lossy branches; the new
passive-tree replay explains and removes the 0.50780 ORO1101 TP29 difference.
The 2023-11-24 bound remains far below its 2.51039 TP29 maximum, which the
separate CPLEX continuation experiment classifies as inherited-basis dual
selection rather than this endpoint-propagation defect.

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

- [`cplex-reference-paths-20190516-highs.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20190516-highs.json`](cplex-reference-comparison-20190516-highs.json)
- [`cplex-reference-paths-20190606-highs.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20190606-highs.json`](cplex-reference-comparison-20190606-highs.json)
- [`cplex-reference-paths-20230922-highs.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs.json`](cplex-reference-comparison-20230922-highs.json)
- [`cplex-reference-paths-20230922-tp29-passive-tree-five-cases.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-tp29-passive-tree-five-cases.json`](cplex-reference-comparison-20230922-tp29-passive-tree-five-cases.json)
- [`cplex-reference-paths-20230922-highs-tp29-corrected.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs-tp29-corrected.json`](cplex-reference-comparison-20230922-highs-tp29-corrected.json)
- [`cplex-reference-paths-20230922-highs-passive-tree-partial.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs-passive-tree-partial.json`](cplex-reference-comparison-20230922-highs-passive-tree-partial.json)
- [`cplex-reference-paths-20230922-highs-passive-tree-tp21.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs-passive-tree-tp21.json`](cplex-reference-comparison-20230922-highs-passive-tree-tp21.json)
- [`cplex-reference-paths-20230922-highs-passive-tree-priority.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs-passive-tree-priority.json`](cplex-reference-comparison-20230922-highs-passive-tree-priority.json)
- [`cplex-reference-paths-20230922-highs-passive-tree-complete.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs-passive-tree-complete.json`](cplex-reference-comparison-20230922-highs-passive-tree-complete.json)
- [`cplex-reference-paths-20230922-tp12-transit-interval.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-tp12-transit-interval.json`](cplex-reference-comparison-20230922-tp12-transit-interval.json)
- [`cplex-reference-paths-20230922-highs-transit-interval.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs-transit-interval.json`](cplex-reference-comparison-20230922-highs-transit-interval.json)
- [`cplex-reference-paths-20230922-tp1-root-boundary-interval.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-tp1-root-boundary-interval.json`](cplex-reference-comparison-20230922-tp1-root-boundary-interval.json)
- [`cplex-reference-paths-20230922-highs-root-boundary-interval.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20230922-highs-root-boundary-interval.json`](cplex-reference-comparison-20230922-highs-root-boundary-interval.json)
- [`cplex-reference-paths-20231124-highs-corrected.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20231124-highs-corrected.json`](cplex-reference-comparison-20231124-highs-corrected.json)
- [`cplex-reference-paths-20231124-tp16-source-disconnection-three-cases.json`](../../../docs/validation/external-evidence.md)
  and [`cplex-reference-comparison-20231124-tp16-source-disconnection-three-cases.json`](cplex-reference-comparison-20231124-tp16-source-disconnection-three-cases.json)

The comparison summaries now retain the identity, observable, CPLEX value,
candidate value, tolerance, and absolute error for each table's maximum. This
makes a maximum auditable even when the first bounded failure examples occur
in earlier cases.
