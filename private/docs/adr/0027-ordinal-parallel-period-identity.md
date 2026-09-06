# ADR-0027: Use ordinal and full period identity for parallel execution

| Field | Decision |
|---|---|
| Status | Accepted for Gate 12 parallel evidence |
| Date | 2026-09-05 |
| Decider | Project owner direction to run ten dynamically assigned workers |

## Context

The 2022-11-17 v5 source legitimately reuses a case label across distinct
date-time/trading-period records. A planner uniqueness check treated the label
as the case identity and rejected the complete inventory.

## Decision

Parallel slicing is defined by the canonical source ordinal. Labels remain
auditable metadata and may recur. Merge uniqueness uses the full
`(case_id, date_time, trading_period)` identity and deterministic ordinal
order. An exact duplicate of that triple still fails closed.

## Consequences

Recurring labels cannot be conflated, omitted, or reordered. Dynamic jobs can
process the complete v5 inventory while preserving deterministic output.

## Rejected alternatives

Dropping repeated labels and suffixing source data with synthetic IDs were
rejected because both alter the Authority identity surface.

## Verification

Planner and merge probity tests distinguish recurring labels by ordinal and
period. The 322-case 2022-11-01 run passes under this policy.

## Revisit triggers

Revisit if the Authority adds another identity dimension or if source order is
no longer stable and hash-bound.
