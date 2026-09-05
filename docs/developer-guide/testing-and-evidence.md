# Testing and evidence

## Probity TDD

For model-affecting work, preserve a red test that fails for the missing or
incorrect behavior before implementing the fix. The evidence record binds:

- requirement/evidence identifier;
- parent and implementation commits;
- test and production paths;
- red and green logs; and
- environment metadata.

Run the evidence audit with:

```shell
uv run python -m tools.probity_audit
```

The audit checks structure and provenance. It does not replace review of whether
the test is scientifically adequate.

## Test layers

| Layer | Purpose |
|---|---|
| Unit | Typed data invariants and one equation/policy behavior |
| Property | Conservation, ordering, bounds and round-trip invariants |
| Matrix | Canonical coefficients, bounds, objective and domain parity |
| Solver | Feasibility, objective, discrete state and finite differences |
| Orchestration | Case ordering, retries, shortfall, publication and checkpoints |
| Report | Identities, fields, units, hashes and reference crosswalk |
| E2E | Full-day/corpus parity under a named execution profile |

## External/oracle tests

Tests marked `oracle` require external GAMS/source artifacts and may be skipped
when those prerequisites are absent. Record the skip reason. Formal evidence
must name the exact source tree, GDX, GAMS executable, solver and license used.

Never substitute a nearby input date for a missing hash-bound oracle input.

## Documentation tests

The documentation build is part of CI:

```shell
uv run mkdocs build --strict
```

Keep commands compatible with `uv`, links relative to `docs`, and examples
honest about whether they are stable CLI, lower-level API, or illustrative
future extension.

## Before committing

```shell
uv run ruff check .
uv run mypy src tools
uv run pytest -q
uv run python -m tools.probity_audit
uv run mkdocs build --strict
git diff --check
```

Long corpus executions need not run on every commit, but their immutable inputs,
configuration, results summary, discrepancy register and hashes must remain
traceable to the implementation they qualify.
