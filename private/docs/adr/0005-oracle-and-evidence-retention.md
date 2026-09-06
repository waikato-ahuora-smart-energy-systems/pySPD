# ADR-0005: oracle and evidence retention

| Field | Value |
|---|---|
| Status | Proposed; oracle selection amended by ADR-0008 |
| Date | 28 August 2026 |
| Deciders | Technical lead, validation lead, data steward, legal reviewer |

## Context

The maintained PySPD implementation needs an independent executable reference.
Final CSV comparisons alone cannot localize preprocessing, model construction,
re-solve, pricing, or reporting differences. However, modifying the oracle for
instrumentation can itself change behavior, and many artifacts may be large or
licence-restricted.

## Decision

Use pinned vSPD v5.0.6 under the qualified ADR-0008 SCIP/HiGHS runtime as the
active interim compatibility oracle, with CPLEX retained as deferred
cross-validation. Retain the source commit/tree/archive hashes and a
separately hashed run-configuration overlay selecting in-scope `SPD`/`AUD`
modes, input files, cases, and periods. The overlay must prevent accidental use
of the pinned settings' `DPS` default.

A governed instrumentation patch emits:

- checkpoints for every material preprocessing transformation;
- active model variant, sets, rows, columns, bounds, fixings, integrality/SOS,
  objective, and matrix before every solve/re-solve;
- primary and any final-pricing solution snapshots, marginals, statuses, logs,
  effective options, and quality information; and
- normalized business/report outputs.

Instrumentation must be observationally neutral: ordinary outputs, statuses,
and solve paths must match a pristine pinned run.

Every gate pack conforms to the
[gate evidence manifest schema](../gate-0/schemas/gate-evidence-manifest.schema.json).
Large/restricted artifacts live in approved immutable storage; Git retains
manifests, schemas, fetchers, synthetic fixtures, and permitted small evidence.

## Consequences

- Defects can be localized to data, preprocessing, algebra, solve, price, or
  report stages.
- Gate 1 requires access to proprietary runtime components.
- Evidence storage, retention, and legal decisions are first-class dependencies.
- Instrumentation changes require separate review and neutrality tests.

## Rejected alternatives

- **Treat PySPD goldens as their own oracle:** circular and unsafe.
- **Compare only final prices:** insufficient structural/control-flow evidence.
- **Commit all GDX/matrix artifacts to Git:** impractical and potentially
  impermissible.
- **Edit pinned source ad hoc:** destroys reproducibility.

## Verification

- Clean environment reproduces every fixture from its manifest.
- Every in-scope family has an executed oracle fixture before Gate 1.
- Pristine/instrumented runs have identical observable outputs and paths.
- Hash verification runs before any artifact is consumed.
- Gate manifests reject unregistered or mutable evidence.

## Revisit triggers

- An Authority-published independent oracle supersedes pinned GAMS vSPD.
- Legal review changes permitted evidence retention.
- A formulation version requires a new oracle profile.
