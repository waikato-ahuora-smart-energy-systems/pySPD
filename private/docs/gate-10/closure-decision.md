# Gate 10 closure decision

## Decision

Gate 10 is **closed — pass at the amended engineering-release-control
boundary**. Stage 11 engineering work is authorized. The candidate remains
`distribution_status: held`, so this is not a public-release authorization.

## Passing basis

- immutable canary comparison and append-only quarantine controls are tested;
- release artifacts, SBOM, evidence, formulations, and legal decisions are
  bound by a tamper-detected manifest;
- the project builds with uv, and the wheel installs and exposes the expected
  CLI from an isolated uv environment;
- macOS CI matches the explicit Linux x86_64 execution deferral;
- user, developer, formulation, data, solver, validation, security, incident,
  support, rollback, and canary procedures are documented; and
- machine validation replaces independent human validation approval under the
  recorded project direction.

## Holds and exclusions

All Gate 0 licence decisions remain pending. The release builder consequently
fails closed to `held`, and no project licence or redistribution permission is
inferred. CPLEX, complete T4, matched full-day performance, and strict E2E
price/report parity remain Gate 12 obligations. Linux x86_64 CI is not run.
