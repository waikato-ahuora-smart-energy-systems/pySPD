# ADR-0016: Clear evidence-ineligible historical transfer-loop residues

| Field | Value |
|---|---|
| Status | Accepted for bounded Gate 12 discovery evidence |
| Date | 1 September 2026 |
| Decider | Project owner direction to continue Gate 12; no separate reviewer required |
| Extends | ADR-0013 and the residue-only condition in ADR-0015 |

## Context

ADR-0015 introduced a general condition that clears shortfall-removal margins
before vSPD's inner transfer loop only when a case has no absolute
`EnergyShortfallMW` above the governed `1e-6 MW` evidence threshold. That
condition was initially packaged with two named 2022-11-24 recovery cases.

The next chronological default-profile date, 2022-11-25, reproduced the same
residue-only loop in its first case, `241012022111100729` at 00:00. The primary
SCIP solve was optimal, no material evidence row was emitted, and five
`0.0002 MW` removal margins remained live. Later cases at 05:45 and 05:50
contained real material transfers plus the same subthreshold companions. This
demonstrates that the control is a population-run discovery-liveness rule
rather than a case-specific numerical workaround.

## Decision

Permit a standalone, hash-addressed historical discovery overlay that:

1. preserves the pinned strict-positive shortfall calculation and the
   `1e-6 MW` material evidence threshold;
2. immediately before the inner transfer loop, clears each
   `ShortfallAdjustmentMW` whose own underlying absolute
   `EnergyShortfallMW <= 1e-6 MW`;
3. preserves every material adjustment and its already-emitted first-loop
   source-to-target evidence, including in mixed material/residue cases;
4. does not create or activate a SCIP option file and therefore retains the
   qualified default solver settings; and
5. admits a date only after the existing exact progress, optimal listing,
   source/patch hash, evidence-schema, and atomic checkpoint validators pass.

The standalone profile is
`historical-v5.0.2-dailymode0-scip-first-loop-material-transfer-subthreshold-residue-threshold1e-6`.

## Consequences

- A cleared residue cannot create or remove a governed affected identity,
  because affected evidence requires an actual first-loop transfer whose
  source shortfall exceeds `1e-6 MW`.
- Any case with one material shortfall still enters the transfer logic with
  every material adjustment intact. Only evidence-ineligible companion
  residues are cleared. ADR-0015 retains its separately hashed 2022-11-24
  exception.
- Default-profile and ADR-0015 checkpoints retain their original patch hashes.
- A partial progress file remains inadmissible; the guard is qualified only
  through complete atomic daily checkpoints.
- The first guarded date, 2022-11-25, passed 282/282 exact optimal selected
  cases and retained five material identities. Its checkpoint logical hash is
  `a9c993352f8ddef9f47933d0276ff7414cb922e26a0acd393ca82e7553deb8c7`.

## Rejected alternatives

- **Add every residue-only or mixed case ID to ADR-0015.** Rejected because the
  cleared values are individually bounded below the material evidence threshold
  and the pathology is demonstrably recurrent.
- **Raise the pinned vSPD strict-positive branch to `1e-6 MW`.** Rejected
  because that would change the general historical formulation rather than
  control an evidence-ineligible loop.
- **Treat the optimal first solve as a complete date.** Rejected because Gate
  12 requires exact canonical daily completion and an atomic checkpoint.

## Verification

- Probity tests require exactly one fail-closed patch point, a distinct
  three-file logical hash, no `scip.opt`, and the exact per-adjustment
  subthreshold condition.
- Daily validation still requires selected count equals solved count, canonical
  progress order, every operational solve optimal, and evidence identities a
  subset of selected cases.
- The final population builder still requires exactly 546 unique identities
  across all 139 hash-bound dates.
- The qualifying 2022-11-25 evidence is indexed by
  `docs/gate-12/historical-residue-recovery-20221125.json`.

## Revisit triggers

- a residue-guarded date changes a material identity relative to a completed
  unguarded run;
- a material adjustment is cleared or the guard changes an emitted material
  row;
- the standalone overlay fails exact checkpoint/repeat validation; or
- the Authority publishes an authoritative affected-case manifest.
