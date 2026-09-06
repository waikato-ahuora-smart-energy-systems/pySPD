# Gate 5 checklist

| Gate criterion | Evidence | Decision |
|---|---|---|
| Matrix structure and coefficients match every AC/loss/security family | [Matrix parity](oracle-matrix-parity.json): identical logical/structural SHA-256; 29,825 rows, 30,084 columns, 73,953 nonzeros; all nine discrepancy counters zero | Pass |
| Branch-flow, bus-balance, loss, capacity, and security residuals pass independently | [Solve/validation evidence](solve-price-validation.json): 29,825 independent checks; maximum residual below `1.1e-10` against `1e-7` | Pass |
| Congestion creates expected price separation and shadow value | Analytic 2-bus capacity case limits flow, produces local deficit marginal, separates bus/node prices, and yields positive rental | Pass |
| Loss breakpoints, segment activation, fixed loss, and direction are correct | Fixed/PWL analytic solve, exact first-segment boundary, forward/reverse block activation, representative 154.99 MW dynamic loss | Pass |
| LE, GE, and EQ constraints cover binding, nonbinding, and violated-with-slack behavior | Parameterized branch and market-node suites cover LE/GE binding and nonbinding, LE/GE violation slacks, EQ exact satisfaction, and both EQ slack directions. “Nonbinding equality” is mathematically inapplicable | Pass |
| Every applicable energy/flow factor type is present | Exact branch-flow and market-node offer factors plus explicit signed demand-bid coefficient test | Pass |
| Topology edge cases match the declared reference behavior | Two/three-bus, reverse, outage/island split, disconnected bus, reference angle, and electrical-dead-node classification tests | Pass |
| Accepted AC/security corpus has no material mismatch | Pinned 923-bus/1,044-branch RTD case has exact matrix and optimal independent validation; analytic stratification covers required edge classes | Pass |
| Node-price transformation is independently validated | Allocation-weighted node prices, dead-node rule, congestion cases, and complete-build `+1e-4 MW` perturbation error below `5.2e-5` NZD/MWh | Pass |
| Probity binds every Gate 5 production path to behavioral red evidence | `TDD-G5-NETWORK`; repository audit reports 25 evidence records and seven covered implementation commits | Pass |
| Qualified platform and exclusions are explicit | macOS arm64/HiGHS qualified; CPLEX deferred by ADR-0008; Linux deferred by ADR-0011 | Pass with stated limitations |

## Verification commands

```text
uv run pytest tests/network -q
uv run python -m tools.gate5.oracle_matrix ...
uv run python -m tools.gate5.qualification ...
uv run python -m tools.probity_audit
uv run pytest -q
uv run ruff check .
uv run mypy src tools
```

All Python/package commands use `uv`. The evidence JSON binds the selected case,
raw GDX, GAMS matrix/dictionary, solver version, tolerances, and semantic hashes.
