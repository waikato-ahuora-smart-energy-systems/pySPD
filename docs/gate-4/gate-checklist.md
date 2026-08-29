# Gate 4 checklist

| Gate criterion | Evidence | Decision |
|---|---|---|
| Canonical core matrix matches the approved Gate 1 Stage 4 projection | [Matrix parity](oracle-matrix-parity.json): identical logical/structural SHA-256; 882 rows, 11,632 columns, 12,892 nonzeros; all nine discrepancy counters zero | Pass |
| Objective components match independently | Independent generation cost, bid benefit, balance/ramp/movement penalty, scarcity cost, system penalty, and net-benefit recomputation; maximum governed error within `1e-7` NZD | Pass |
| Analytic dispatch, objective, slack, and price cases match hand results | Merit order, negative price, zero price, elastic demand, signed demand, capacity, scarcity, ramp-up/down, conflicting cap, and infeasible-with-slack tests | Pass |
| Balance and ramp residuals meet thresholds | Independent evaluator plus representative full RTD evidence; maximum residual below `5e-13` MW against `1e-7` MW | Pass |
| Price sign, units, duration, complementarity, and finite-difference meaning are correct | Negative/zero/positive/scarcity tests; `NZD/MWh` convention; revenue conversion `price × minutes/60`; analytic complementarity zero; full RTD dual/finite-difference maximum error below `2e-5` | Pass |
| Solver economic invariants agree under the approved profile | HiGHS optimal result and GAMS Stage 4 matrix oracle agree; ADR-0008 explicitly defers native CPLEX, so this is a qualified-profile pass and not a CPLEX claim | Pass with stated limitation |
| Joint-batch independence | Joint-batch extension is not enabled | Not applicable |
| Repeated builds are structurally identical and immutable | Repeated semantic matrix hashes/signatures equal; distinct models; Gate 3 source hash unchanged | Pass |
| Component, policy, schema, and renderer extensions work through public interfaces | Synthetic extensions execute without changing `ModelAssembler` or unrelated classes | Pass |
| Probity binds every Gate 4 production path to prior behavioral red evidence | `TDD-G4-CORE` and `TDD-G4-ORACLE`; repository audit reports 24 records and six covered implementation commits | Pass |
| Qualified platform and exclusions are explicit | macOS arm64/HiGHS qualified; CPLEX deferred by ADR-0008; Linux deferred by ADR-0011 | Pass with stated limitations |

## Verification commands

```text
uv run pytest tests/core_energy -q
uv run python -m tools.gate4.oracle_matrix ...
uv run python -m tools.gate4.qualification ...
uv run python -m tools.gate3.oracle_parity ...
uv run python -m tools.probity_audit
uv run pytest -q
uv run ruff check .
uv run mypy src tools
```

All Python/package commands use `uv`. The evidence JSON files bind the selected
case, GDX files, GAMS matrix/dictionary files, solver version/options,
tolerances, and logical hashes.
