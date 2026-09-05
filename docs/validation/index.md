# Validation workflow

Validation is a chain of evidence, not a single solver status.

## Recommended ladder

### 1. Input integrity

- verify the GDX SHA-256;
- select the explicit input schema;
- validate required symbols and dimensions with `SymbolCatalog`;
- retain special values and source UEL ordering; and
- reject an incomplete or ambiguous case inventory.

### 2. Preprocessing parity

Compare normalized sets and parameters before solving. Pay particular attention
to study mode, demand reconstruction, offer/ramp units, topology, branch loss
segments, reserve risks, scarcity activation, and daily shortfall rules.

### 3. Algebra and matrix evidence

For changed components, compare canonical variables, rows, bounds,
coefficients, objective terms, and SOS/discrete domains. A matching objective on
one case cannot prove that the matrices are equivalent.

### 4. Independent physical checks

Check energy balance, branch flow/loss relationships, offer and ramp bounds,
HVDC equations, reserve requirements, risk coverage, and fixed-discrete
consistency independently of the primary solve implementation.

### 5. Objective and primal results

Require complete/optimal cases, then compare objective, violations, generation,
reserve, demand, branch flow, and loss surfaces. Explain material differences
before relying on prices.

### 6. Prices

Compare fixed-RMIP objective and state, raw balance duals, repaired bus prices,
node allocation, reserve prices, and publication aggregation. Apply analytical
interval containment only where the interval has independent evidence.

### 7. Reports and provenance

Compare complete identity sets before values. Verify report hashes, row counts,
units, source/configuration/dependency provenance, repeatability, and any
checkpoint/resume equivalence.

## Local quality commands

```shell
uv sync --frozen --group docs
uv run ruff check .
uv run mypy src tools
uv run pytest -q
uv run python -m tools.probity_audit
uv run mkdocs build --strict
```

Oracle-marked tests require external GAMS/source prerequisites and may be
skipped in an ordinary development environment. A skip is not passing oracle
evidence. The large historical corpus is restored through the
[external-evidence workflow](external-evidence.md), with every archive checked
against the tracked SHA-256 manifest before extraction.

## Evidence pack for a new case study

Retain:

- question, scope and predeclared acceptance criteria;
- source URI/path, byte size and SHA-256;
- case inventory and selection procedure;
- formulation, input schema, solver profile and worker count;
- canonical scenario JSON and hash;
- code commit and `uv.lock` hash;
- runtime versions and host architecture;
- console logs and timings;
- report bundle and manifest hash;
- comparison summary plus full discrepancy records; and
- disposition for every material discrepancy.

The [Gate 12 checklist](../gate-12/gate-checklist.md) is the controlling model
for end-to-end historical parity.
