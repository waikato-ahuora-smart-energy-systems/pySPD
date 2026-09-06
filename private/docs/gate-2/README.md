# Gate 2 — data and LP foundation

| Field | Value |
|---|---|
| Gate | G2 — Data and LP foundation ready |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Current decision | **CLOSED — PASS FOR MACOS ARM64 PROFILE** |
| Gate 1 dependency | Closed by commit `c10c522` |
| Linux scope | Deferred by ADR-0011; no Linux claim |

## Implemented foundation

- installable, typed `src/pyspd` package managed exclusively with `uv`;
- immutable runtime configuration, case identifier, `CaseData`, result schema,
  result record, and result-set contracts;
- immutable `RawSymbols`, `RawSymbol`, `RawRecord`, and explicit scalar kinds
  for finite, EPS, NA, UNDEF, positive/negative infinity, and text values;
- GAMS-free Arrow/Parquet canonical archive and scalable per-symbol feed with
  one source record per row, lazy case loading, confined artifact paths, and
  separate physical and encoding-independent logical SHA-256 validation;
- optional GAMS Transfer adapter that classifies special values before numeric
  coercion;
- a versioned 43-family vSPD v5.0.6 source catalog, including current daily and
  historical selected-case aliases, domains, units, missingness, ordering, and
  consumer ownership;
- class contracts for formulations, model components, preprocessors, solve
  policies, pricing engines, result schemas, and report renderers;
- actionable pre-model schema, case/date, reference, allocation, and ordered
  curve validation, including property and mutated-invalid tests;
- deterministic dependency-ordered `ModelAssembler` with missing-provider,
  cycle, duplicate-owner, returned-handle, formulation-version, and sealed
  artifact checks and a deterministic structural signature;
- a Pyomo APPSI HiGHS continuous-LP backend with version/options capture,
  normalized statuses, fail-closed nonoptimal behavior, and explicit safe
  solution loading; and
- a JSON-Schema-backed Probity ledger validator and repository coverage auditor
  that reject wrong parent,
  implementation, environment, test, production-path, output, behavioral-red,
  exception-expiry evidence, historical test-blob drift, and uncovered changed
  production paths.

## Qualification evidence

[Canonical characterization](canonical-characterization.json) binds a selected
2022 RTD input to its raw hash, 43-symbol/14,676-record representation, stable
logical hash, and PyArrow 22 Parquet hash. Its canonical archive was read back
without using the GAMS adapter and compared equal to `RawSymbols`.

[Canonical feed qualification](canonical-feed-qualification.json) records the
exact selected-RTD cross-reader comparison and a full daily benchmark. Direct
feed conversion reduced observed peak RSS from 6,399,148,032 bytes to
673,415,168 bytes and elapsed time from 44.31 seconds to 14.37 seconds for
3,873,677 source records.

[Corpus qualification](corpus-qualification.json) binds all 139 source hashes,
537,880,618 converted records, 139 feed hashes, and semantic validation of 278
boundary cases. There were no rejected inputs.

[Environment qualification](environment-qualification.json) records successful
clean `uv sync --frozen` creation for every declared group. The default runtime
loaded a 42-symbol canonical feed and 14,896-record case with no `gams` module
installed.

## Gate checklist

| Criterion | Evidence | State |
|---|---|---|
| In-scope symbols documented | Versioned 43-family catalog and catalog tests | Pass |
| Record identity/order/value fidelity | Full official-reader conversion plus exact independent selected-RTD comparison | Pass |
| Canonical round trip and special values | Archive/feed tests and characterization | Pass |
| Encoding-independent logical hashes | Zstandard/Snappy fixture with fixed logical hash | Pass on qualified macOS platform |
| Explicit reproducible GDX boundary | Source-SHA-bound governed canonical feed | Pass |
| Every qualification input handled | 139/139 qualified; zero rejected | Pass |
| Routine GAMS-free loading | Fresh default environment check | Pass |
| Invalid data fails before construction | Schema/semantic/property tests | Pass |
| Frozen `uv` environments | Default, GDX, oracle, docs, Gurobi, deferred-empty CPLEX | Pass |
| Continuous LP backend contracts | HiGHS availability/version/options/status/safe-load tests | Pass |
| Deterministic class assembly | Dependency, ownership, formulation, sealing, signature tests | Pass |
| Probity evidence and changed-path audit | 14 bound records plus repository audit | Pass |
| Linux x86_64 release target | Configured CI matrix; ADR-0011 | Deferred outside qualified profile |

CPLEX validation remains explicitly deferred by ADR-0008 and project direction;
no CPLEX-specific parity claim is made. Gurobi installation is qualified only as
an optional dependency, not as a validated solver backend.

## Closure decision

All Gate 2 criteria within the qualified macOS arm64 profile pass. The project
explicitly directed that Linux x86_64 execution be skipped; ADR-0011 preserves
that limitation and prohibits a Linux claim. There are no unexplained data,
runtime, solver-contract, architecture, corpus, or Probity blockers.

Gate 2 is closed and Stage 3 is authorized.
