# Gate 9 closure decision

## Decision

Gate 9 is **closed — pass** for the amended macOS arm64,
GAMS-SCIP/fixed-discrete-HiGHS engineering release-candidate boundary. Gate 10
engineering packaging and operations work is authorized.

## Passing basis

1. The explicit v5 formulation selects its own daily result schema and report
   renderer classes; no effective-date switch chooses a hidden formulation.
2. All twelve report families have typed ordered fields and units, immutable
   rows, deterministic serialization, per-file hashes, row counts, and a
   configuration/provenance-bound manifest.
3. The public API and CLI reject unknown formulations, unknown configuration
   fields, missing inputs, and source-hash changes before a solve.
4. Structural signatures include active variable domains, row shape, SOS,
   objective sense, component graph, extensions, and artifact ownership.
5. The pinned official RTD case completed through the public CLI and produced
   all report families after an official-case domain defect was captured red,
   fixed, and rerun green.
6. Published prices, reserve/island reports, report schemas, identity sets, and
   row counts were exact on repeat. Detailed primary outputs were classified as
   alternative-optimum surfaces under SCIP rather than hidden.
7. `uv sync --frozen`, `uv sync --frozen --group oracle`, the full test suite,
   Ruff, mypy, and the Probity repository audit pass.

## Amended boundary and Gate 12 carry-forward

The original Gate 9 text assumed CPLEX, organizationally independent sign-off,
complete T4 acquisition/replay, complete-day performance comparison, and strict
published-report parity. Project direction already defers CPLEX and removes the
independent reviewer requirement. The complete T4, complete-day performance,
full physical determinism, and strict E2E parity obligations are transferred to
Gate 12 and remain fail-closed there.

This decision permits the maturity label **validated engineering release
candidate (SCIP/HiGHS profile)**. It does not permit `validated vSPD parity`,
`CPLEX compatible`, `production release`, or `publicly distributable` claims.
