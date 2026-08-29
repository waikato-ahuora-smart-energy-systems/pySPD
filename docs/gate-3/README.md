# Gate 3 — deterministic preprocessing parity

| Field | Value |
|---|---|
| Gate | G3 — Preprocessing equivalent |
| Started | 29 August 2026 |
| Current decision | Qualification candidate; Probity binding and closure audit pending |
| Gate 2 dependency | Closed by commit `a9cb728` |
| Qualified platform | macOS arm64 |
| Linux scope | Deferred by ADR-0011; no Linux claim |

The implementation is a class-composed, immutable preprocessing pipeline for
the pinned `vspd-v5.0.6` formulation. The [source map](source-map.md) binds each
in-scope GAMS block to its Python owner, named artifacts, and focused tests.

Current executable qualification evidence:

- [oracle parity](oracle-parity.json): 64 GAMS/Python derived families, exact
  key parity, zero value mismatches, and maximum absolute error zero;
- [corpus invariants](corpus-invariants.json): all 139 governed daily feeds,
  278 chronological boundary cases, repeated deterministic checkpoints, and
  zero violations across 3,403,918 independent invariant observations; and
- 30 focused preprocessing tests covering hand examples, effective dates,
  RTD/schedule load behavior, mapped-node rules, settings branches, invalid
  inputs, immutability, relabeling, and meaningful order changes.

Formal closure requires the implementation commit to be bound by the Gate 3
Probity ledger and a final repository-wide verification run.
