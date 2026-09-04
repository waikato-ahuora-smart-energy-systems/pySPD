# 2023-09-22 passive-tree progressive validation

## Outcome

The generalized passive zero-flow tree correction has now been replayed in
canonical order for all 274 cases and all 48 trading periods on 2023-09-22.
Every case reports an optimal SCIP MIP followed by HiGHS fixed-RMIP solve;
there were no retries. Solver time was 3,202.66 seconds and wall time was
3,872.95 seconds.

Forty-seven of the 48 periods have zero unresolved published-energy differences
at the Authority's stored precision. All 167 unresolved published-energy rows
are confined to TP4. TP1 retains two SI reserve-price differences; TP4 retains
one SI FIR-price difference; nine summary values remain above stored
precision. TP12 ATU1101's scalar differs from CPLEX by
0.06490 NZD/MWh, but the difference is independently certified by the
multi-boundary passive-transit interval.

| Period | Cases | Energy unresolved | Energy interval-certified | Maximum scalar energy difference (NZD/MWh) | Reserve unresolved | Summary unresolved |
|---|---:|---:|---:|---:|---:|---:|
| TP1 | 7 | 0 | 363 | 0.02355 | 2 | 6 |
| TP10 | 6 | 0 | 2 | 0.18343 | 0 | 0 |
| TP12 | 6 | 0 | 2 | 0.12104 | 0 | 0 |
| TP13 | 6 | 0 | 1 | 0.14727 | 0 | 0 |
| TP14 | 6 | 0 | 2 | 0.25478 | 0 | 0 |
| TP15 | 6 | 0 | 1 | 0.19278 | 0 | 0 |
| TP16 | 6 | 0 | 1 | 0.01143 | 0 | 0 |
| TP19 | 6 | 0 | 0 | <0.00001 | 0 | 0 |
| TP20 | 6 | 0 | 0 | <0.00001 | 0 | 0 |
| TP21 | 6 | 0 | 1 | 0.17462 | 0 | 0 |
| TP24 | 6 | 0 | 0 | <0.00001 | 0 | 0 |
| TP25 | 6 | 0 | 1 | 0.02304 | 0 | 0 |
| TP26 | 6 | 0 | 1 | 0.00886 | 0 | 0 |
| TP29 | 5 | 0 | 0 | <0.00001 | 0 | 0 |
| TP30 | 6 | 0 | 0 | <0.00001 | 0 | 0 |
| TP33 | 6 | 0 | 2 | 0.25713 | 0 | 0 |

The maximum scalar difference is retained even when certified. It is not an
unresolved error. For example, TP33 ORO1101 selects the governed export value
147.31281 NZD/MWh, while CPLEX reports 147.56994 NZD/MWh. The publication
weights propagate the case-level analytic bounds to
[147.31281, 148.51970] NZD/MWh, which contains the CPLEX value.

## Evidence-path correction

`PublishedPriceAccumulator` already calculated weighted node-price intervals,
but the solver-path summary serializer and JSONL merge/substitution tools
dropped them. The corrected evidence path now:

1. serializes `price_interval` on published energy rows;
2. reconstructs weighted lower and upper numerators from durable per-case node
   rows when shards or replacement streams are aggregated;
3. preserves an empty interval for reserve rows; and
4. certifies a scalar CPLEX difference only when the rounded reference price
   lies inside the source-derived interval, allowing the governed publication
   tolerance.

Malformed, reversed, duplicate, or non-finite intervals fail closed. The
selected scalar convention remains `export`; no CPLEX-specific endpoint rule
has been introduced.

The same containment rule governs every canonical price surface that carries
an analytic interval: repaired bus prices, branch endpoint bus prices, node
prices, daily averaged node prices, and published energy prices. Any reference
value inside the source-derived interval is accepted as dual-equivalent; a
value outside it remains an unresolved failure. The governed price/display
tolerance is allowed only at the interval boundaries. Empty intervals continue
to require ordinary scalar parity.

## Cumulative boundary

The cumulative partial-rerun stream remains complete at 274 cases by retaining
the earlier records for periods not yet replayed. It is bound by
[`cplex-reference-paths-20230922-highs-passive-tree-partial.json`](cplex-reference-paths-20230922-highs-passive-tree-partial.json)
and compared in
[`cplex-reference-comparison-20230922-highs-passive-tree-partial.json`](cplex-reference-comparison-20230922-highs-passive-tree-partial.json).

Under the current v7 interval-aware validator, the TP1/TP12-substituted
complete stream has 29,631 above-precision rows and 10,044 certified
differences across 3,964,736 mapped values. At the published-energy boundary,
536 differences are interval-certified and 167 remain unresolved. TP21
ORO1101 is no longer
unresolved: CPLEX's 112.04301 NZD/MWh lies inside the weighted analytic
interval [111.86839, 113.03644] NZD/MWh.

TP12's six-case rerun is bound by
[`cplex-reference-paths-20230922-tp12-transit-interval.json`](cplex-reference-paths-20230922-tp12-transit-interval.json)
and
[`cplex-reference-comparison-20230922-tp12-transit-interval.json`](cplex-reference-comparison-20230922-tp12-transit-interval.json).
TP1's seven-case rerun is bound by
[`cplex-reference-paths-20230922-tp1-root-boundary-interval.json`](cplex-reference-paths-20230922-tp1-root-boundary-interval.json)
and
[`cplex-reference-comparison-20230922-tp1-root-boundary-interval.json`](cplex-reference-comparison-20230922-tp1-root-boundary-interval.json).
The updated complete stream is bound by
[`cplex-reference-paths-20230922-highs-root-boundary-interval.json`](cplex-reference-paths-20230922-highs-root-boundary-interval.json)
and
[`cplex-reference-comparison-20230922-highs-root-boundary-interval.json`](cplex-reference-comparison-20230922-highs-root-boundary-interval.json).
It substitutes only those thirteen freshly solved TP1 and TP12 records into
the prior complete 274-case stream and inherits the other 261 solves and the
recorded timing.

The six-case result and its cumulative substitution are bound by
[`cplex-reference-paths-20230922-tp21-passive-tree-six-cases.json`](cplex-reference-paths-20230922-tp21-passive-tree-six-cases.json),
[`cplex-reference-comparison-20230922-tp21-passive-tree-six-cases.json`](cplex-reference-comparison-20230922-tp21-passive-tree-six-cases.json),
[`cplex-reference-paths-20230922-highs-passive-tree-tp21.json`](cplex-reference-paths-20230922-highs-passive-tree-tp21.json),
and
[`cplex-reference-comparison-20230922-highs-passive-tree-tp21.json`](cplex-reference-comparison-20230922-highs-passive-tree-tp21.json).

The four-period priority batch and its cumulative substitution are bound by
the TP13, TP24, TP26, and TP30 `paths`/`comparison` pairs and by
[`cplex-reference-paths-20230922-highs-passive-tree-priority.json`](cplex-reference-paths-20230922-highs-passive-tree-priority.json)
and
[`cplex-reference-comparison-20230922-highs-passive-tree-priority.json`](cplex-reference-comparison-20230922-highs-passive-tree-priority.json).

The authoritative full-day replay is bound by
[`cplex-reference-paths-20230922-highs-passive-tree-complete.json`](cplex-reference-paths-20230922-highs-passive-tree-complete.json)
and
[`cplex-reference-comparison-20230922-highs-passive-tree-complete.json`](cplex-reference-comparison-20230922-highs-passive-tree-complete.json).

## Next execution

Diagnose the remaining coupled price cluster: TP1's two SI reserve
publications, and TP4's 167 energy and one SI FIR publication. Unlike the
zero-flow energy certificates, the TP4 difference also changes reserve
sharing and summary cost and must not be classified as a node-only dual
interval. TP24's two TUI offers also require a narrow source-backed
alternate-energy-allocation certificate: their total generation and marginal
block cost agree, but CPLEX and SCIP split 4.7 MW of identical-price
second-block energy differently. All certifications must preserve the raw
numeric differences and fail closed outside their proven equivalence class.
