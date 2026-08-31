# ADR-0013: Discover the Gate 12 shortfall population with recomputed RTD load

| Field | Value |
|---|---|
| Status | Accepted by project direction |
| Date | 30 August 2026 |
| Decider | Project owner direction to proceed with Gate 12; no separate reviewer required |
| Supersedes | The exact-positive discovery interpretation documented during early Gate 12 execution |

## Context

The vSPD v5.0.4 release declares 546 affected RTD intervals across 139 trading
dates but does not publish their case IDs. The defect occurs in daily mode: after
a shortfall transfer, v5.0.2 can retain stale input demand instead of
recalculating RTD load for the final solve.

A first Gate 12 oracle retained `dailymode = 1` and treated every
strict-positive eligible-removal predicate as membership. GAMS `EPS` residues
then produced `0.0002 MW` removal-margin adjustments for routine cases. The
profile emitted 737 identities across only three dates and therefore could not
represent the declared population.

The Gate 1 non-daily exact fixture and independent algebraic reconstruction
show the required distinction. Non-daily RTD calculation exposes material
shortfall at affected nodes; daily mode's stale demand can suppress that signal,
which is the behavior the later replay must test.

## Decision

Use a separately named population-discovery profile with all of these rules:

1. pin vSPD v5.0.2 commit
   `3360a91ebd48f2e3cbb52a5e6766d893011054be`;
2. set `dailymode = 0` only for identity discovery so the pinned RTD load is
   recomputed;
3. select only canonical RTD modes 101 and 201 in GDX order;
4. solve the first historical shortfall decision with SCIP and require an
   optimal result;
5. leave the historical `EnergyShortfallMW > 0` branch unchanged;
6. emit evidence only after `ShortfallTransferFromTo` selects an actual target
   and only when source shortfall exceeds `1e-6 MW`;
7. bind source, patch, listing, progress, transfer evidence, and checkpoint
   hashes; and
8. reject the profile immediately if cumulative membership exceeds 546.

This profile discovers identities only. It does not prove the daily-mode defect
state machine or PySPD parity. Every emitted identity must subsequently be
replayed through pinned daily-mode GAMS and PySPD with the canonical same-day
prefix.

## Consequences

- GAMS `EPS` truthiness remains present in the historical solve but cannot by
  itself create population membership.
- Evidence includes both source and target nodes, adjustment quantity, solve
  loop, and optimal model/solver statuses.
- The 434-case algebraic result remains a diagnostic lower bound; the exact
  SCIP screen can discover solver-dependent cases that the algebraic screen
  omitted.
- Enumeration remains compute-intensive and resumable across the 139
  hash-bound inputs.
- Five completed default-profile checkpoints remain valid for their exact
  dates. The next date, 2022-11-24, exposed a reproducible SCIP optimum whose
  unscaled `OAM_T1.T1` branch-block row violated the original GAMS model by
  `0.00034560206410994 MW`, leaving GAMS indefinitely in post-solve processing.
- Global `numerics/feastol` trials at `1e-9` and `1e-10` are rejected as the
  population profile. Both still produced GAMS-rejected original-model
  residuals (about `1.22e-7` and `1.26e-7` respectively), and the latter made
  population execution impractically slow. Their workspaces are calibration
  evidence only and produced no accepted checkpoints.
- Recovery for 2022-11-24 must be narrowly targeted and separately
  hash-addressed; it cannot relabel or alter the five completed checkpoints.
  The governed trial leaves option files disabled for every ordinary solve and
  loads `emphasis: numerics` plus `numerics/feastol = 1e-10` only when the loop
  case ID is `241012022111000704`. The entire one-date shard must still pass;
  a successful target solve alone is not a checkpoint.
- Gate 12 remains open until the resulting manifest contains exactly 546 cases
  and all separate E2E criteria pass.

## Rejected alternatives

- **Daily-mode eligible-removal predicates.** Rejected because three dates
  already produce 737 false memberships from EPS-scale residues.
- **Apply `1e-6 MW` to the historical branch.** Rejected because it changes the
  state machine being observed.
- **Promote the 434 analytic candidates.** Rejected because an exact SCIP solve
  has demonstrated an analytic/relaxed false negative.
- **Treat discovery as daily-mode parity evidence.** Rejected because
  `dailymode = 0` is used only to reveal membership; daily-mode replay remains a
  separate Gate 12 obligation.

## Verification

- Probity tests require exact source patch points and reject schema drift,
  missing target nodes, EPS-scale records, later-loop records, non-optimal
  solves, noncanonical order, source/hash drift, and population overrun.
- `historical-exact-positive-invalidation.json` binds the three-date overrun
  that rejected the predecessor selector.
- The canonical 2022-11-06 qualification must reproduce the four cases already
  observed by the independent algebraic reconstruction before full execution.
- The final builder must still reject any result other than exactly 546 unique
  identities covering all 139 source hashes.
- Targeted numerics probity tests require a numeric case ID, exact injection at
  all three pinned MIP solve statements, an exact option file, and a distinct
  four-file patch hash. CLI/workspace profile disagreement fails closed.

## Revisit triggers

- the canonical 2022-11-06 exact profile does not reproduce the four expected
  candidate identities;
- the completed population does not contain exactly 546 unique identities;
- the Authority publishes an authoritative case-ID list with different
  membership; or
- later daily-mode replay shows that the discovery criterion does not bind the
  disclosed defect path.
