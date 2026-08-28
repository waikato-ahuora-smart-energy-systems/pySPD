# Gate 2 — data and LP foundation

| Field | Value |
|---|---|
| Gate | G2 — Data and LP foundation ready |
| Started | 29 August 2026 |
| Current decision | **IN PROGRESS — NOT CLOSED** |
| Gate 1 dependency | Closed by commit `c10c522` |

## Implemented checkpoint

- installable, typed `src/pyspd` package managed exclusively with `uv`;
- immutable `RawSymbols`, `RawSymbol`, `RawRecord`, and explicit scalar kinds
  for finite, EPS, NA, UNDEF, positive/negative infinity, and text values;
- GAMS-free Arrow/Parquet canonical archive with separate physical and stable
  logical SHA-256 validation;
- optional GAMS Transfer adapter that classifies special values before numeric
  coercion;
- a versioned 43-family vSPD v5.0.6 source catalog, including current daily and
  historical selected-case aliases, domains, units, missingness, ordering, and
  consumer ownership;
- class contracts for formulations, model components, preprocessors, solve
  policies, pricing engines, result schemas, and report renderers;
- deterministic dependency-ordered `ModelAssembler` with missing-provider,
  cycle, duplicate-owner, returned-handle, formulation-version, and sealed
  artifact checks;
- a Pyomo APPSI HiGHS continuous-LP backend with version/options capture,
  normalized statuses, fail-closed nonoptimal behavior, and explicit safe
  solution loading; and
- a JSON-Schema-backed Probity ledger validator that rejects wrong parent,
  implementation, environment, test, production-path, output, behavioral-red,
  and exception-expiry evidence.

## Executed RTD characterization

[Canonical characterization](canonical-characterization.json) binds a selected
2022 RTD input to its raw hash, 43-symbol/14,676-record representation, stable
logical hash, and PyArrow 22 Parquet hash. Its canonical archive was read back
without using the GAMS adapter and compared equal to `RawSymbols`.

## Remaining before Gate 2 closure

- finish typed `CaseData`, configuration, identifiers, and concrete result data
  contracts;
- add cross-reader/cross-version physical-encoding tests while retaining the
  same logical hash;
- implement domain, allocation, ordered-block, curve, date/case, and permissible
  missingness validators with mutated-invalid/property tests;
- execute schema and round-trip qualification across the complete Gate 2
  corpus, recording approved per-file rejections if any;
- test unavailable, unbounded, limit, error, and no-solution backend paths;
- execute clean `uv sync --frozen` checks for every supported dependency group;
- retain and validate immutable red/green evidence for each production slice;
  and
- perform the formal Gate 2 checklist and blocker audit.

Stage 3 is not authorized until this remaining work is complete and Gate 2 is
formally closed.
