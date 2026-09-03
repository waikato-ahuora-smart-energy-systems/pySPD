# Ten-day CPLEX zero-flow price analysis

## Outcome

The expanded CPLEX corpus contains 1,731 solved cases and 217,680 passive
simple-leaf observations with zero branch flow, branch loss, fixed loss, leaf
generation, and leaf load. Of the observations whose prices distinguish the
two analytic loss-kink endpoints, CPLEX selected:

- the export endpoint 76,443 times (82.13%); and
- the load endpoint 16,632 times (17.87%).

Another 124,605 observations have equal or numerically indistinguishable
endpoints and are classified as ambiguous. The added four days preserve the
earlier conclusion: the CPLEX endpoint is basis-dependent and no stable static
topology rule reproduces every stored raw dual.

## Propagation and materiality

Of the 16,632 CPLEX load-endpoint choices, 16,376 (98.46%) have no nonzero
market-node allocation and affect only raw bus/branch reporting. The remaining
256 case-node observations reach four nodes: `BPT1101`, `KIN1009`, `RFN1102`,
and `WPT1101`. Across all identifiable node-projected endpoints, CPLEX chose
export 3,422 times and load 256 times, so the governed export endpoint matches
93.04% of node-relevant choices.

| Day | Cases | Export | Load | Load reaching nodes | Maximum raw-bus change | Maximum base-node change | Maximum published change |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019-02-18 | 48 | 1,331 | 1,161 | 32 | 2.083151 | 0.522081 | n/a |
| 2019-05-16 | 48 | 1,549 | 1,186 | 28 | 1.526987 | 0.072508 | n/a |
| 2019-06-05 | 48 | 1,491 | 1,165 | 35 | 3.277611 | 0.289394 | n/a |
| 2019-06-06 | 48 | 1,477 | 1,209 | 32 | 1.917013 | 0.083150 | n/a |
| 2019-06-22 | 48 | 1,503 | 1,233 | 23 | 1.425678 | 0.067769 | n/a |
| 2023-01-26 | 294 | 14,583 | 1,495 | 23 | 2.912546 | 0.045250 | 0.049390 |
| 2023-02-14 | 321 | 14,046 | 3,137 | 36 | 1.179203 | 0.012865 | 0.013722 |
| 2023-08-02 | 305 | 14,620 | 1,831 | 16 | 9.170335 | 0.018580 | 0.016657 |
| 2023-09-22 | 274 | 11,475 | 2,102 | 18 | 1.909254 | 0.023974 | 0.023038 |
| 2023-11-24 | 297 | 14,368 | 2,113 | 13 | 3.727093 | 0.025283 | 0.030708 |

All differences are NZD/MWh. They are predicted changes caused solely by
normalizing a stored CPLEX load endpoint to the deterministic export endpoint;
they are not a general bound on solver or formulation differences. In
particular, the observed new-day published maxima of 0.50780 and 2.51039
NZD/MWh exceed the corresponding analytic predictions and remain unresolved.

## Governed treatment

PySPD continues to expose the deterministic export value as scalar `price`
and the exact analytic interval as `price_interval: [lower, upper]` where the
source topology proves a passive zero-injection loss kink. This treatment:

1. keeps primal optimization and basis-dependent output parity separate;
2. certifies only prices inside a source-derived interval;
3. projects the interval through node allocations and publication weights; and
4. leaves every residual CPLEX difference visible.

The machine-readable evidence is
[`cplex-zero-flow-analysis-ten-days.json`](cplex-zero-flow-analysis-ten-days.json).
It is regenerated with:

```bash
uv run --group gdx python -m tools.analyze_cplex_zero_flow \
  --corpus tests/fixtures/cplex_reference \
  --system-directory /path/to/gams/system/directory \
  --output docs/gate-12/cplex-zero-flow-analysis-ten-days.json
```
