# Gate 8 — Daily orchestration and market post-processing

| Field | Value |
|---|---|
| Gate | G8 — End-to-end behavior equivalent |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Decision | **CLOSED — PASS FOR AMENDED CURRENT EVIDENCE BOUNDARY** |
| Gate 7 dependency | Closed by commit `df32ff6` |
| Implementation | `93d4991` with behavioral contract fix `3c45b7e` |
| Primary MIP | SCIP through licensed GAMS 54; optimum required |
| Pricing RMIP | Fix all discrete variables, relax all discrete domains, HiGHS solve |
| CPLEX | Deferred by ADR-0008; official price differences reported separately |
| Linux | Deferred by ADR-0011; no Linux execution claim |

The class-based Stage 8 implementation is complete. It selects RTD/PRSS cases
and publication durations from GDX record order, enforces model compatibility,
prepares the full Gate 7 formulation, applies all eleven override families in
pinned family/scope order, carries prior accepted dispatch into a zero next-case
start, and runs a bounded shortfall-transfer/scaling-disable state machine. The
runner retains immutable events, raw/repaired/node/reserve price layers,
degraded states, and configuration-bound resumable checkpoints.

The pinned representative case reaches the same primary and fixed-RMIP
objective as Gate 7 through the required GAMS-SCIP → fix 124 discrete variables
→ HiGHS path. Independent price allocation and publication recomputation passes
1,209 checks at a maximum residual of `1.78e-15`. All 523 energy and four
reserve identities match the reference identity sets.

Gate 8 closes on the project-owner-approved current evidence boundary. The
Authority release gives 546 affected RTD intervals and 139 dates but no case
identifiers. Direct replay of the corrected GDX dead-node/positive-load
predicate identifies 427 immutable cases,
all hash-bound to the Gate 1 files, leaving 119 active-node shortfall cases
unidentified. The public release has no assets containing the missing IDs. The
exact 546-identity manifest, exhaustive replay, and representative full-day
economic parity are mandatory Gate 12 work and are not claimed here.

The separate official-price comparison is also retained rather than hidden:
the cross-solver profile differs at 163 of 523 energy nodes above `1e-4`
NZD/MWh (maximum `1.23576`) and two of four reserve prices (maximum `0.0746`),
despite matching objective economics and independent publication identities.
This is classified as a solver/basis-sensitive official-price difference under
the approved non-CPLEX profile, not as an error in allocation or weighting.
Strict price/report parity remains a Gate 12 obligation.

See the [source map](source-map.md), [gate checklist](gate-checklist.md),
[decision record](closure-decision.md),
[machine-readable amended acceptance](amended-acceptance.json),
[end-to-end qualification](end-to-end-qualification.json), and
[partial interval screen](shortfall-interval-manifest.json). The carried-forward
obligations are controlled by the [Gate 12 reference](../gate-12/README.md).
