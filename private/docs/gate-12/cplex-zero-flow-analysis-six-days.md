# Six-day CPLEX zero-flow price analysis

## Outcome

The six supplied CPLEX days contain 1,064 solved cases and 132,486 passive
simple-leaf observations with zero branch flow, zero branch loss, zero fixed
loss, zero leaf generation and zero leaf load. Of the observations whose
reported prices distinguish the two loss-kink endpoints, CPLEX selected:

- the export endpoint 47,574 times (82.60%); and
- the load endpoint 10,022 times (17.40%).

The selection is not stable by branch, date, declared branch orientation, or
the preceding nonzero flow direction. Of 336 recurring branch/leaf groups on
2023-08-02, 130 switch endpoint during the day. The previous nonzero-flow
direction predicts only 6 of 179 identifiable subsequent choices. This is
consistent with a basis-dependent dual and rules out a reliable static
topology formula for reproducing every historical CPLEX row.

## Propagation and materiality

The export normalization differs from CPLEX only where CPLEX selected the load
endpoint. Of those 10,022 observations, 9,857 (98.35%) have no nonzero market-
node allocation. They appear only in raw bus/branch reporting and have no role
in dispatch, objective value, node prices, or published prices.

Only 165 case-node observations propagate through the source GDX allocation
matrix. They affect four nodes: `BPT1101`, `KIN1009`, `RFN1102`, and `WPT1101`.
Among all identifiable node-projected endpoints, CPLEX selected export 2,313
times and load 165 times, so the export convention matches 93.34% of the
node-relevant CPLEX choices.

| Day | Cases | Export | Load | Load values reaching nodes | Largest new raw-bus difference | Largest new base-node difference | Largest new published difference |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019-02-18 | 48 | 1,331 | 1,161 | 32 | 2.083151 | 0.522081 | n/a |
| 2019-06-05 | 48 | 1,491 | 1,165 | 35 | 3.277611 | 0.289394 | n/a |
| 2019-06-22 | 48 | 1,503 | 1,233 | 23 | 1.425678 | 0.067769 | n/a |
| 2023-01-26 | 294 | 14,583 | 1,495 | 23 | 2.912546 | 0.045250 | 0.049390 |
| 2023-02-14 | 321 | 14,046 | 3,137 | 36 | 1.179203 | 0.012865 | 0.013722 |
| 2023-08-02 | 305 | 14,620 | 1,831 | 16 | 9.170335 | 0.018580 | 0.016657 |

All monetary values are NZD/MWh. The large raw-bus maxima occur at
`FHL_WPW2.1` and have no node allocation. Every largest node or publication
change in the table occurs at `WPT1101`. The 2019 corpus does not contain the
published-price tables introduced in the 2023 result set.

These are predicted differences caused solely by replacing a stored CPLEX
load endpoint with the deterministic export endpoint. For parent price `p`
and stored load endpoint `l`, the corresponding export endpoint is `p²/l`.
No optimization rerun is required because this transformation is applied only
after the fixed-RMIP solution and cannot alter primal variables or its
objective.

## Generic treatment

CPLEX remains the numerical gold standard. The generic treatment separates two
claims that cannot safely be conflated:

1. **Optimization correctness:** a price is accepted as dual-equivalent only
   after source topology proves a passive zero-injection leaf, zero flow/loss,
   one positive-loss boundary, and a price within the analytic interval between
   the export and load endpoints. Such a price is excluded from dispatch and
   objective correctness failures because it has no role in the primal optimum.
2. **Output parity:** PySPD reports the deterministic export endpoint, which
   matches the dominant CPLEX choice and eliminates the former 0.49680 WPT1101
   publication discrepancy. Any remaining CPLEX numeric difference at a
   certified kink remains visible, is projected through node allocations and
   publication weights, and is never silently discarded.

PySPD now preserves both truths in its output contract. The deterministic
export value remains the scalar `price`, while affected bus, node, and
published-energy results also carry `price_interval: [lower, upper]`. The
interval is computed from the source loss factors, not inferred from the CPLEX
result. Differentiable prices have no interval field. No endpoint-selection or
solver-convention label is emitted.

Exact reproduction of every historical raw dual would require the original
CPLEX matrix order, presolve, options and basis sequence. The installed GAMSPy
license includes full CPLEX and provides a route for a future fixed-RMIP CPLEX
backend, but using the same solver version alone does not prove the same basis.

## Evidence and reproducibility

The machine-readable result is
[`cplex-zero-flow-analysis-six-days.json`](cplex-zero-flow-analysis-six-days.json).
It can be regenerated with:

```bash
uv run --group gdx python -m tools.analyze_cplex_zero_flow \
  --corpus tests/fixtures/cplex_reference \
  --system-directory /path/to/gams/system/directory \
  --output docs/gate-12/cplex-zero-flow-analysis-six-days.json
```

The analysis uses the CPLEX branch and bus rows for passivity and endpoint
prices, and independently reads node allocations and publication seconds from
each source GDX. Equal/lossless endpoint prices are classified as ambiguous and
do not contribute to predicted differences.
