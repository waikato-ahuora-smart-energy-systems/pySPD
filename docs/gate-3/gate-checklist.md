# Gate 3 checklist

| Gate criterion | Evidence | Decision |
|---|---|---|
| Every in-scope source block maps to a named transformation and test | [Source map](source-map.md), ADR-0012, 35 focused tests | Pass |
| Derived memberships, mappings, flags, bounds, and coefficients match the oracle | [Oracle parity](oracle-parity.json): 64 families, zero missing/extra keys, zero mismatches, maximum absolute error zero | Pass |
| Every supported date regime has before/on/after cases | Nine explicit boundary cases around 2019-03-28, 2023-04-27, and 2025-03-17 | Pass |
| Required-load reconstruction covers RTD, schedule, and price-responsive cases | Hand-derived RTD target/scaling test, schedule non-application test, ramp-cap unit/oracle evidence, pure mapped-node resolver tests | Pass |
| Override order/effects are deterministic and logged | Ordered scale/increment/value test; immutable per-key before/after provenance | Pass |
| Label renaming preserves economics and meaningful order changes remain visible | Hypothesis/property tests plus relabeling and changed block-ordinal metamorphic tests | Pass |
| Whole governed corpus passes independent invariants | [Corpus evidence](corpus-invariants.json): 139 feeds, 278 cases, 3,403,918 observations, zero violations and zero nondeterminism | Pass |
| No unexplained preprocessing discrepancy remains | Exact selected-RTD checkpoint parity and zero corpus failures | Pass |
| Probity TDD binds all Gate 3 production paths | Eight Gate 3 records; all-gate auditor reports 22 total records and four covered implementation commits | Pass |
| Qualified execution profile is explicit | macOS arm64 qualified; Linux x86_64 deferred by ADR-0011 | Pass with stated limitation |

## Verification commands

```text
uv run pytest tests/preprocess -q
uv run python -m tools.gate3.oracle_parity ...
uv run python -m tools.gate3.corpus ...
uv run python -m tools.probity_audit
uv run pytest -q
uv run ruff check .
uv run mypy src tools
```

The full oracle and corpus commands, source hashes, case identities, precision
rule, checkpoint hashes, and case evidence hashes are retained in the linked
JSON evidence. All package/runtime commands use `uv`.
