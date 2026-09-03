# 2023-09-22 passive-tree progressive validation

## Outcome

The generalized passive zero-flow tree correction has been replayed for 59 of
the 274 cases on 2023-09-22. The refreshed inventory covers TP10, TP12, TP14,
TP15, TP16, TP19, TP20, TP25, TP29, and TP33. Every case reports an optimal
SCIP MIP followed by HiGHS fixed-RMIP solve.

Nine of the ten targeted periods have zero unresolved published-energy,
published-reserve, and summary differences at the Authority's stored
precision. TP12 retains one unrelated published-energy residual at ATU1101 of
0.06490 NZD/MWh. Its original ORO1101 error is removed, and its ORO1102 value
is independently contained by the analytic interval.

| Period | Cases | Energy unresolved | Energy interval-certified | Maximum scalar energy difference (NZD/MWh) | Reserve unresolved | Summary unresolved |
|---|---:|---:|---:|---:|---:|---:|
| TP10 | 6 | 0 | 2 | 0.18343 | 0 | 0 |
| TP12 | 6 | 1 | 1 | 0.12104 | 0 | 0 |
| TP14 | 6 | 0 | 2 | 0.25478 | 0 | 0 |
| TP15 | 6 | 0 | 1 | 0.19278 | 0 | 0 |
| TP16 | 6 | 0 | 1 | 0.01143 | 0 | 0 |
| TP19 | 6 | 0 | 0 | <0.00001 | 0 | 0 |
| TP20 | 6 | 0 | 0 | <0.00001 | 0 | 0 |
| TP25 | 6 | 0 | 1 | 0.02304 | 0 | 0 |
| TP29 | 5 | 0 | 0 | <0.00001 | 0 | 0 |
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

Relative to the original complete-day comparison, the total above-precision
count falls from 34,438 to 34,237. At the published-energy boundary, 522
differences are interval-certified and 188 remain unresolved in periods that
mostly still contain pre-correction records. The next unresolved published
maximum is TP21 ORO1101 at 0.17462 NZD/MWh. A complete 274-case rerun is still
required before the day can be certified as a current-model result.

## Next execution

Continue the compare-as-you-go replay with TP21, TP24, TP26, TP30, and TP13,
then run the remaining periods and replace the partial stream with one complete
current-model solve. Reassess TP12 ATU1101 and the three published-reserve and
nine summary residuals only after that complete rerun.
