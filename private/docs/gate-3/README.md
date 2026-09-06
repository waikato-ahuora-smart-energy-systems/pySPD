# Gate 3 — deterministic preprocessing parity

| Field | Value |
|---|---|
| Gate | G3 — Preprocessing equivalent |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Current decision | **CLOSED — PASS FOR MACOS ARM64 PROFILE** |
| Gate 2 dependency | Closed by commit `a9cb728` |
| Qualified platform | macOS arm64 |
| Linux scope | Deferred by ADR-0011; no Linux claim |

The implementation is a class-composed, immutable preprocessing pipeline for
the pinned `vspd-v5.0.6` formulation. The [source map](source-map.md) binds each
in-scope GAMS block to its Python owner, named artifacts, and focused tests.

Executable qualification evidence:

- [oracle parity](oracle-parity.json): 64 GAMS/Python derived families, exact
  key parity, zero value mismatches, and maximum absolute error zero;
- [corpus invariants](corpus-invariants.json): all 139 governed daily feeds,
  278 chronological boundary cases, repeated deterministic checkpoints, and
  zero violations across 3,403,918 independent invariant observations; and
- 35 focused preprocessing tests covering hand examples, effective dates,
  RTD/schedule load behavior, mapped-node rules, settings branches, invalid
  inputs, immutability, relabeling, and meaningful order changes.

Repository-wide verification passes with 120 tests and one
declared optional-integration skip. The fail-closed repository audit validates
22 Gate 2/3 Probity records across four implementation commits; eight Gate 3
records cover every changed Gate 3 production path, including the all-gate
auditor itself.

See the [gate checklist](gate-checklist.md) and
[closure decision](closure-decision.md). Gate 3 is closed and Stage 4 is
authorized. Linux x86_64 execution remains explicitly deferred and no Linux
claim is made.
