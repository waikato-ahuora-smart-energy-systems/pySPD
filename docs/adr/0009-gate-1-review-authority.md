# ADR-0009: Gate 1 review authority

| Field | Value |
|---|---|
| Status | Accepted by project direction |
| Date | 29 August 2026 |
| Decider | Project owner direction recorded in the development task |

## Context

The Gate 1 checklist and closure audit treated appointment and approval by an
independent validation reviewer as a mandatory hold. Project direction states
that no independent validation reviewer or independent approval is required
for Gate 1.

## Decision

Remove independent-review appointment and approval from Gate 1 entry and exit
criteria. Gate 1 remains evidence-driven: every technical criterion, immutable
artifact, discrepancy classification, and reproducibility requirement still
applies. The project owner may direct closure after the technical checklist has
no mandatory hold or unexplained oracle self-inconsistency.

This decision is scoped to Gate 1. It does not silently change later release or
external-assurance claims in Gates 9 and 10.

## Consequences

- The absence of an independent reviewer is not a Gate 1 blocker.
- Technical evidence cannot be waived merely because review is not required.
- Gate 1 closure can proceed once the remaining corpus, instrumentation,
  comparator, tolerance, and performance criteria are met.

## Verification

- Gate 1 documents classify independent review as not required.
- The closure decision contains only technical blockers.
- No Gate 1 pass is recorded while a technical hold remains.

## Revisit triggers

- Project direction reinstates independent Gate 1 review.
- The intended claim expands to an assurance label that explicitly requires
  organizational or external independence.
