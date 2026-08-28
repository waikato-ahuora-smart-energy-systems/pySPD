# ADR-0010: Date-level shortfall-transfer qualification at Gate 1

| Field | Value |
|---|---|
| Status | Accepted by project direction |
| Date | 29 August 2026 |
| Decider | Project owner direction recorded in the development task |

## Context

The vSPD v5.0.4 release identifies a corrected population of 546 RTD intervals
across 139 trading dates, but does not publish the exact case IDs. All 139
official corrected daily GDX inputs have been acquired and individually bound
by size and SHA-256. Static post-fix inputs cannot establish which schedule IDs
would have taken the pre-fix shortfall-transfer path.

An attempted relaxed-HiGHS selector was rejected after an exact SCIP solve
demonstrated a false negative. Exhaustive discrete replay can identify the
population, but that work tests the daily shortfall-transfer state machine that
is implemented in Stage 8. Requiring its complete execution before Stage 2
would duplicate the Gate 8 end-to-end criterion before the Pyomo data and model
layers exist.

## Decision

Gate 1 qualifies the shortfall-transfer population at date level when all of
the following evidence exists:

1. all 139 corrected official daily GDX inputs are acquired and individually
   hash-bound;
2. an exact, optimal SCIP fixture exercises the affected shortfall-transfer,
   maximum-loop, and cleanup/re-solve path;
3. the frozen RTD/PRSS/AUD corpus supplies ordinary controls and the comparator
   evidence required by the other Gate 1 criteria; and
4. representative 46- and 50-trading-period daylight-saving fixtures execute
   successfully under the accepted reference profile.

Exact identification and replay of all 546 affected interval IDs is assigned
to Stage 8 and remains a mandatory Gate 8 exit criterion. The T3 corpus retains
the 546-interval/139-date scope. This decision changes the timing of exhaustive
replay, not the population or the eventual equivalence claim.

The accepted Gate 1 reference remains optimal SCIP MIP followed, where prices
are required, by fixed-discrete HiGHS RMIP under ADR-0008. CPLEX validation
remains deferred.

## Consequences

- The absence of a published exact case-ID list is not a Gate 1 blocker once
  the four date-level conditions above are met.
- Gate 1 can close without claiming that all 546 intervals have already been
  replayed.
- Stage 8 must identify or otherwise bind each of the 546 intervals and execute
  its approved assertions before Gate 8 can pass.
- A missing, substituted, or hash-changed daily input reopens the Gate 1
  population qualification until the discrepancy is governed.
- A relaxed LP screen cannot be used as evidence of interval membership.

## Rejected alternatives

- **Treat the relaxed HiGHS screen as exhaustive.** Rejected because an exact
  SCIP solve produced a demonstrated false negative.
- **Hold Gate 1 until the Authority publishes exact IDs.** Rejected because no
  such list is present in the public release and the complete daily inputs are
  already immutable and available for Stage 8 replay.
- **Run exhaustive discrete enumeration in Gate 1.** Rejected as misplaced
  end-to-end orchestration validation; the obligation remains mandatory at
  Gate 8.
- **Reduce the final population claim to representative fixtures.** Rejected;
  all 546 intervals remain in Gate 8 and the T3 defect/history corpus.

## Verification

- `docs/gate-1/shortfall-input-inventory.json` contains exactly 139 unique
  entries and its logical inventory hash is recorded by the closure evidence.
- `docs/gate-1/shortfall-characterization.json` binds the exact optimal affected
  fixture and records the rejected relaxed selector.
- `docs/gate-1/daylight-saving-characterization.json` binds successful 46- and
  50-period fixtures.
- The Gate 1 checklist records date-level qualification and the Gate 8 plan
  retains the all-546 pass criterion.

## Revisit triggers

- the Authority publishes an authoritative exact 546-case list;
- a retained daily input changes hash or provenance;
- exact Stage 8 replay finds an unrepresented reference branch that invalidates
  Gate 1 comparator or oracle assumptions; or
- the release claim expands to assert all-546 replay before Gate 8 evidence
  exists.
