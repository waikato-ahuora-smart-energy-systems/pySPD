# ADR-0015: Recover pathological historical discovery cases without widening the oracle

| Field | Value |
|---|---|
| Status | Accepted for bounded Gate 12 recovery evidence |
| Date | 1 September 2026 |
| Decider | Project owner direction to continue Gate 12; no separate reviewer required |
| Constrains | ADR-0013 for explicitly named recovery cases only |

## Context

ADR-0013 preserves the pinned vSPD v5.0.2 strict-positive shortfall branch and
uses `1e-6 MW` only as an evidence-emission threshold. Five dates completed
under that qualified default profile. On 2022-11-24, case
`241012022111000704` returned a SCIP optimum but GAMS rejected the scaled
solution against the original model. Global numerical changes were either
still rejected or too slow and therefore cannot replace the default profile.

Case-only `1e-11` and `1e-12` profiles were not stable: SCIP could terminate
with unresolved LP numerical trouble. Using HiGHS as SCIP's LP engine did not
remove that failure. Retaining `numerics/feastol = 1e-10` while tightening only
the incumbent check progressively reduced the rejected original-model
residual. At `numerics/checkfeastolfac = 1e-4`, vSPD accepted the target solve
and emitted a first-loop `ABY0111` to `TIM1101` transfer of
`2.259244594868 MW`. Case `241012022111005708` emitted the same transfer
identity at `0.204906717115 MW`. Both cases then retained strict-positive,
sub-`1e-6 MW` margin adjustments that could keep the inner loop live.

## Decision

Permit one separately hash-addressed recovery profile with both interventions:

1. load `numerics/feastol = 1e-10` and
   `numerics/checkfeastolfac = 1e-4`, without broad numerical emphasis, only
   for case `241012022111000704`;
2. immediately before the shortfall-transfer loop, and only for cases
   `241012022111000704` and `241012022111005708`, set
   `ShortfallAdjustmentMW` to zero where the
   underlying absolute `EnergyShortfallMW` is at or below `1e-6 MW`;
3. retain material adjustments, target selection, evidence emission, all other
   cases, and the canonical GDX order unchanged;
4. in any case where the maximum absolute shortfall is at or below `1e-6 MW`,
   clear all adjustments before the transfer loop because that case cannot emit
   a governed population identity;
5. execute the whole trading date in nonqualifying shard scope; and
6. admit the date for population identity discovery only if the existing exact
   progress, optimal-listing, evidence-schema, source-hash, patch-hash, and
   atomic-checkpoint validators all pass.

This exception does not qualify the modified residue path as pinned vSPD state
parity. Every discovered material identity remains subject to the separate
daily-mode GAMS/PySPD replay required by Gate 12.

## Consequences

- The five default-profile checkpoints remain unchanged and retain their
  original patch hash.
- The completed recovery checkpoint carries a distinct profile and
  four-file patch hash; it cannot be silently merged under the default profile.
- No case can be added to the population from a cleared residue. Evidence still
  requires an actual selected transfer whose source shortfall exceeds
  `1e-6 MW`.
- The general residue-only condition cannot run when any material shortfall is
  present, so it cannot change a material source or transfer target. The named
  23:00 and 23:05 exceptions remain separately visible because both cases mix
  material evidence and residues.
- The recovery is intentionally case-specific. Discovery of the same pathology
  elsewhere requires another explicit decision and hash-addressed profile.
- The completed shard contains 261/261 exact optimal selected cases and two
  governed identities. Its logical checkpoint hash is
  `fa975ac86c2e32a8bde72d904fb8b0d016ebe7811cb67795d7dd1dc939c323ed`.
- A successful target solve or emitted row was insufficient; admission required
  the complete atomic daily checkpoint recorded in
  `docs/gate-12/historical-targeted-recovery-20221124.json`.

## Rejected alternatives

- **Change the global SCIP tolerance.** Rejected because it invalidates five
  completed profiles, remains numerically unreliable, and is too slow.
- **Apply `1e-6 MW` to every historical shortfall branch.** Rejected because it
  changes the general oracle rather than recovering one demonstrated loop.
- **Accept the partial progress/evidence files.** Rejected because they lack a
  complete canonical date and immutable checkpoint.
- **Treat SCIP optimality alone as population evidence.** Rejected because
  identity discovery also requires the selected material source-to-target
  transfer.

## Verification

- Probity tests require numeric case IDs, an admissible SCIP tolerance, exact
  pinned patch points, and distinct logical hashes for each recovery profile.
- The material-only statement must occur exactly once and be guarded by the
  named case ID.
- The one-date run must contain exactly the canonical selected cases, one
  first-success progress identity per case, only optimal listing records, and
  material evidence that is a subset of those cases.
- The final 139-date builder still requires exactly 546 unique identities and
  cannot infer membership from this ADR.

## Revisit triggers

- the guarded one-date checkpoint fails hash or resume validation;
- the same residue-loop pathology appears in another case;
- the guarded case's material identity differs from an unmodified successful
  run; or
- the Authority publishes an authoritative affected-case manifest.
