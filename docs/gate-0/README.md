# Gate 0 baseline and decision pack

| Field | Value |
|---|---|
| Gate | G0 — Baseline authorized |
| Pack version | 0.2 |
| Date | 29 August 2026 |
| Status | Engineering baseline complete — **GOVERNANCE HOLD** |
| Decision authority | Gate 0 signatories, currently unassigned |
| Governing plan | [PySPD stage-and-gate reference](../pyomo-vspd-stage-gate-plan.md) |

## Purpose

This pack converts Stage 0 of the governing plan into reviewable decisions,
registers, schemas, and acceptance evidence. Its engineering preparation is
complete and project direction on 29 August 2026 authorized Gate 1 research
and characterization. It does not claim the legal, market-SME, independent
validation, or release approvals that only named reviewers can provide.

The release-governance decision remains **HOLD** because named owners, legal
approval, and archived governing-document hashes are not yet available. GAMS
54.3.1 and the full-size SCIP/HiGHS active reference are executed and evidenced;
native CPLEX is deferred cross-validation under ADR-0008.

## Pack contents

| Artifact | Purpose | Status |
|---|---|---|
| [Project charter](charter.md) | Mission, claim, principles, governance, and release boundary | Candidate |
| [Scope and feature matrix](scope-and-feature-matrix.md) | In-scope, deferred, and excluded capabilities | Candidate |
| [Source register](source-register.json) | Machine-readable source identities, hashes, and archive state | Partial: external hashes pending |
| [Formulation reconciliation](formulation-reconciliation.md) | v15 intent-to-v5 source map and v16 delta boundary | Draft; SME review required |
| [Compatibility matrix](compatibility-matrix.md) | Data, runtime, solver, platform, and case-type profiles | SCIP/HiGHS characterization qualified |
| [Validation baseline](validation-baseline.md) | Initial corpus, comparator, tolerance, discrepancy, and claim policy | Candidate |
| [Licence and provenance register](licence-and-provenance-register.md) | Legal questions and artifact-handling controls | **HOLD: legal review required** |
| [Risk and dependency register](risk-and-dependency-register.md) | Gate risks, dependencies, owners, and controls | Open |
| [Roles and sign-off](roles-and-signoff.md) | Required accountabilities and approval record | **HOLD: roles unassigned** |
| [Gate checklist](gate-checklist.md) | Criterion-by-criterion decision evidence | **HOLD** |
| [Candidate evidence manifest](pack-manifest.json) | Machine-readable immutable index of this candidate pack | **HOLD** |
| [TDD evidence schema](schemas/tdd-evidence.schema.json) | Auditable red/green TDD record | Proposed |
| [Gate evidence manifest schema](schemas/gate-evidence-manifest.schema.json) | Immutable evidence-pack index | Proposed |
| [ADR index](../adr/README.md) | Proposed architecture and assurance decisions | Proposed |

## Proposed decisions

The pack proposes that PySPD:

1. qualifies pinned vSPD v5.0.6 first;
2. uses SPD Formulation v15 as governing context for v5 Link Risk and AC
   Secondary Risk behavior;
3. treats SPD v16 as a separately selected formulation, never a silent patch;
4. uses class-based composition around a Pyomo `ConcreteModel`;
5. treats optimal GAMS/SCIP plus fixed-discrete GAMS/HiGHS as the active interim
   compatibility oracle and defers CPLEX-specific validation;
6. treats HiGHS as LP-only until every required SOS reformulation passes Gate 6
   and Gate 7 evidence;
7. uses a GAMS-free canonical data layer with explicit GAMS special-value
   semantics;
8. characterizes MIP pricing at Gate 1 instead of assuming `solvefinal` behavior;
9. uses `uv` exclusively for Python package and command management; and
10. requires Probity guardrails plus immutable red/green CI evidence for TDD.

## Current holds

| Hold | Closure evidence |
|---|---|
| Sponsor and accountable roles are unassigned | Completed and signed [roles record](roles-and-signoff.md) |
| Legal/provenance interpretation is unapproved | Signed legal review against the [licence register](licence-and-provenance-register.md) |
| Governing PDFs are not archived and hashed | Updated [source register](source-register.json) with immutable hashes and archive locations |
| v15-to-v5 clause reconciliation is not independently reviewed | SME-approved [reconciliation register](formulation-reconciliation.md) |
| Initial tolerance and corpus policy is not signed | Validation lead and market SME approval of [validation baseline](validation-baseline.md) |

## Approval procedure

1. Close every mandatory hold or record a non-material conditional action.
2. Review each proposed ADR and set it to `Accepted` or `Rejected`.
3. Freeze external artifacts and update their hashes.
4. Complete the gate checklist with links to immutable evidence.
5. Obtain all required signatures.
6. Record `PASS`, `CONDITIONAL PASS`, `HOLD`, or `RESET` in the checklist.

Gate 1 oracle research and characterization may proceed under the restrictions
in the governing plan. No production formulation or release-compatibility
claim is authorized while the governance holds remain open.
