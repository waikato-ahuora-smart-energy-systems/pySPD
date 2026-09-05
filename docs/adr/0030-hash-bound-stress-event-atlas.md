# ADR-0030: Build stress-event atlases from preregistered, hash-bound corpora

| Field | Decision |
|---|---|
| Status | Accepted by explicit project direction |
| Date | 2026-09-06 |
| Decider | Project owner direction to implement case-study item 3 |

## Context

The retained historical corpus contains unusual and control days, but selection
reasons and numerical signals were distributed across fixture manifests and
Gate 12 evidence. Choosing an event after inspecting results can bias a case
study, and labels such as “stress” or “outage” can overstate what an output
table alone establishes.

## Decision

A historical stress-event atlas begins with an immutable preregistration that
declares the complete source-manifest population, exclusions, thresholds,
categories, causal boundary, and output location. The class-based builder:

- includes every unique result-backed day in the declared manifests;
- verifies the input and result-tree SHA-256 values;
- validates expected result row and DST period counts;
- extracts stable summary, node, reserve, and branch metrics;
- classifies only against registered thresholds; and
- writes deterministic JSON, CSV, and Markdown views with a logical hash.

DST labels may be declared from the corpus selection record and are confirmed
against period count. Other measured categories are not inferred from prose.

## Consequences

The v1 atlas covers 21 CPLEX-backed days and provides a reproducible queue for
causal counterfactual studies. It does not classify result-free inputs, infer
outages or islanding, or treat case-level sums as settlement totals. A new
threshold or population requires a new preregistration and study ID.

## Rejected alternatives

- Hand-picking visually interesting days was rejected because it is not
  reproducible and hides the denominator.
- Inferring all categories from manifest prose was rejected after the phrase
  “zero-violation” demonstrated a false-positive risk.
- Running PySPD first and selecting only close CPLEX matches was rejected as
  outcome-dependent sampling.

## Verification

Unit tests cover metric extraction, threshold classification, source and period
fail-closed behavior, deduplication, conflict detection, deterministic output,
and logical hashing. The retained evidence test fixes the 21-day population and
registered category counts. A full rebuild verifies all large-file hashes.

## Revisit triggers

Revisit when an additional CPLEX corpus is retained, when PySPD output becomes
an independently qualified atlas source, or when topology-aware input analysis
can support explicit outage and islanding categories.
