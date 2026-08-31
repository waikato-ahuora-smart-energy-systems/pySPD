# ADR-0014: Replay and compare Gate 12 dates incrementally

| Field | Value |
|---|---|
| Status | Accepted by project direction |
| Date | 30 August 2026 |
| Decider | Project owner direction to compare completed dates as discovery proceeds |

## Context

Gate 12 population discovery is a long, resumable screen of 139 hash-bound
daily inputs. The original execution sequence deferred all pinned-GAMS and
PySPD replays until the exact 546-identity manifest existed. That ordering was
safe but created a large validation backlog and delayed discovery of replay or
parity defects.

A completed daily population checkpoint already binds the source, solver
profile, canonical case order, optimality, shortfall-transfer evidence, and its
own logical hash. It therefore contains enough immutable evidence to derive
that date's replay prefix without waiting for the other 138 dates.

## Decision

Process Gate 12 as a checkpoint-driven pipeline:

1. accept only the contiguous inventory-ordered prefix of complete discovery
   checkpoints;
2. recheck the governed GDX size and SHA-256 before every new replay;
3. derive the canonical same-day prefix through the last affected case;
4. run the pinned daily-mode GAMS reference and PySPD candidate independently;
5. export exactly twelve canonical affected-case surfaces from each engine;
6. compare the two bundles and atomically save a date-level parity checkpoint;
7. reuse a checkpoint only when its source, discovery checkpoint, replay work
   item, processor profile, and zero-discrepancy disposition all still match;
8. persist a failed comparison and stop rather than skipping it; and
9. aggregate the date-level checkpoints only after the full 546-case population
   has independently passed its existing gate.

Within a PySPD date, preparation and execution are streamed in canonical case
order. Each completed case atomically records the exact continuation state:
predecessor generation, event sequence, unrounded publication accumulators,
case ordinal, and configuration/work-item hashes. An affected case additionally
records eleven canonical surfaces before its solved Pyomo model is released.
Only the rounded published-output surface and published-price report rows are
deferred until the prefix is complete. The twelve-surface date bundle is still
published atomically and is never inferred from a partial checkpoint.

The PySPD producer uses the explicit
`scip-mip-fixed-highs-rmip` application profile. GAMS reference production
remains independently identifiable and may be serialized with discovery when
the installed network entitlement permits only one active GAMS session.
PySPD invokes SCIP through Pyomo's native PySCIPOpt adapter and therefore does
not consume the GAMS network entitlement; HiGHS remains the separate fixed-RMIP
pricing solver.

The portable solver contract keeps SCIP's explicit `1e-6` primal-feasibility
tolerance. Before the independent HiGHS solve, SOS members lying within `1e-5`
of zero or one are projected to that exact boundary in the primary evidence
snapshot. Only zero-valued (inactive) SOS members are fixed in the pricing
model; active interpolation weights remain continuous and are reoptimised
within the interval selected by the separately fixed portable binaries. This
removes solver-feasibility residue, preserves SOS support, and avoids
over-constraining the RMIP. The independent objective validator retains the
absolute residual as evidence and applies the declared tolerance to both
absolute and scale-relative objective agreement.

The preprocessing mode is also part of the replay contract. Pinned
`vSPDsolve.gms` guards RTD required-load reconstruction with `dailymode = 0`.
Consequently, canonical daily replay retains the source demand and does not run
the non-daily RTD reconstruction before the first solve. The shortfall loop may
still transfer load and re-solve when the daily solve itself exposes an eligible
shortfall. It does not re-solve merely to disable RTD load scaling, because that
flag cannot change a daily-mode model instance. These distinctions are covered
by Probity TDD because applying the non-daily reconstruction, or its
scaling-disable re-solve, in PySPD created false daily transitions and changed
accepted load, dispatch, objective, and prices.

## Consequences

- Replay defects become visible on the first completed date instead of after
  the complete population screen.
- Discovery, reference, candidate, and comparison artifacts remain separately
  hash-addressed; pipelining does not turn discovery output into parity proof.
- A missing earlier checkpoint prevents later dates from being processed, so
  predecessor order cannot be silently bypassed.
- Existing successful date-level parity work survives interruption and restart.
- Completed cases within a long date also survive interruption without retaining
  every solved Pyomo model in memory.
- Exact canonical-byte comparison is a deliberately strict initial processor.
  The later semantic processor is separately named
  `gams-pyspd-semantic-tolerance-v1`, hash-binds its hexadecimal policy and both
  bundle hashes, and preserves the exact result unchanged. It accepts only
  declared numeric tolerance, sparse numeric zero, a qualified diagnostic raw
  SCIP objective, and raw-price sentinels whose corresponding repaired
  economics pass. Report schema drift and above-tolerance prices remain
  unresolved with bounded case/path evidence.
- A separately hash-bound source-matrix certificate may select the distinct
  `gams-pyspd-semantic-tolerance-bus-certified-v1` profile. It must reproduce
  the observed node-price delta by projecting both engines' bus-price delta
  through the original GDX node-allocation matrix. It may normalize a differing
  raw `+/-500000` sentinel only when the same repaired bus agrees. The
  certificate cannot resolve report, publication, missing-identity, or
  non-numeric differences.
- A published-price alternative certificate must predeclare and bind its
  warmup/period case set, require optimal complete cases and zero predecessor
  fallback, and retain a failed result. Observing one favorable run after an
  unfavorable governed run is diagnostic solver variability, not permission to
  select the favorable output as parity evidence.
- The final Gate 12 decision remains fail-closed at exactly 546 identities over
  all 139 dates, complete representative-day coverage, and zero unresolved
  material discrepancies.

## Rejected alternatives

- **Wait for the final manifest.** Rejected because it delays useful replay and
  parity feedback without strengthening a completed daily checkpoint.
- **Replay isolated affected cases.** Rejected because same-day predecessor
  dispatch and publication state would be omitted.
- **Run dates past a missing checkpoint.** Rejected because it weakens ordered
  provenance and complicates restart semantics.
- **Reuse failed parity checkpoints.** Rejected because a persisted failure is
  diagnostic evidence, not successful completion.

## Verification

Probity tests cover canonical prefix derivation, ordered availability, source
and checkpoint drift, atomic bundle and checkpoint writes, all twelve surface
hashes, exact continuation-float round trips, within-date interruption and
resume, missing or tampered artifacts, idempotent restart, processor-profile
separation, and persisted comparison failure.
