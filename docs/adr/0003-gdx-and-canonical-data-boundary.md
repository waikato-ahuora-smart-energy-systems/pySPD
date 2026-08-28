# ADR-0003: GDX and canonical data boundary

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 28 August 2026 |
| Deciders | Data lead, technical lead, validation lead, legal reviewer |

## Context

GDX records carry ordered labels, domains, sparse presence, and GAMS special
values. Ordinary DataFrame/Parquet handling can collapse absent versus stored
zero, normalize signed zero, or lose distinctions among EPS, NA, and UNDEF.
Requiring GAMS in every PySPD runtime would also undermine portability.

## Decision

Adopt two explicit data layers:

1. `RawSymbols`: a faithful, versioned GDX semantic model preserving symbol
   type, dimension, domains, UEL order, descriptions, record presence, and value
   identity.
2. Canonical data: a GAMS-free representation, expected to use Parquet/Arrow
   plus manifests, consumed by normal PySPD runs.

Canonical records encode at least:

```text
present
value_kind = finite | eps | na | undef | positive_infinity | negative_infinity
numeric_value
```

NaN payloads and signed zero are not authoritative semantic carriers. Each
conversion records both a physical-file hash and a stable logical-content hash.

The production GDX reader remains an implementation selection for Stage 2. The
qualified user path must be one of:

- local official-GDX conversion without a GAMS licence; or
- a governed conversion service/artifact feed mapping raw hashes to canonical
  hashes.

GAMS Transfer may serve as a reference/migration adapter but is not a mandatory
normal-runtime dependency.

## Consequences

- PySPD can run from canonical inputs without GAMS.
- Conversion is a separately versioned, testable supply-chain step.
- Storage is larger/more explicit than naive numeric Parquet.
- A conversion service may be required if a reliable GAMS-free reader is not
  qualified.

## Rejected alternatives

- **Read GDX directly inside model classes:** couples I/O, semantics, and Pyomo.
- **Convert missing records to zero:** changes active domains and coefficients.
- **Represent EPS solely as `-0.0`:** not stable across serializers.
- **Require GAMS everywhere:** incompatible with the portability objective.
- **Treat 42 symbols as permanent:** v5 schema already evolves by effective date.

## Verification

- Exact cross-reader symbol/domain/order/presence comparisons.
- Special-value round trips across supported OS/library versions.
- Stable logical hashes despite permitted physical encoding differences.
- Invalid domain/order/curve cases fail before model construction.
- Every qualification GDX converts or has a specific approved rejection.

## Revisit triggers

- An open-source GDX reader is qualified across the full corpus.
- Canonical schema evolution is required by a new source/formulation.
- Legal review changes permitted storage or distribution.
