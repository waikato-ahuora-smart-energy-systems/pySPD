# Gate 0 decision checklist

| Field | Value |
|---|---|
| Gate | G0 — Baseline authorized |
| Review version | 0.2 |
| Current decision | **ENGINEERING COMPLETE; GOVERNANCE HOLD** |
| Review date | 29 August 2026 |
| Gate chair | TBD |

## Criteria

| ID | Mandatory criterion | Evidence | State | Blocking action |
|---|---|---|---|---|
| `G0-01` | Exact v5.0.6 commit and reference artifacts are immutable and retrievable | [Source register](source-register.json) | Partial | Move source archive to approved immutable storage; archive/hash external documents |
| `G0-02` | SPD Formulation v15 applicable clauses are reconciled to pinned v5 source | [Reconciliation register](formulation-reconciliation.md) | **Hold** | Complete clause-level mapping and SME/validation review |
| `G0-03` | Legal review permits planned development, evidence retention, and release | [Licence register](licence-and-provenance-register.md) | **Hold** | Qualified reviewer decides all critical rows |
| `G0-04` | v16 is explicitly separate from v5 compatibility | [ADR-0001](../adr/0001-formulation-baseline-and-versioning.md), [delta register](formulation-reconciliation.md) | Candidate met | Accept ADR and reconciliation boundary |
| `G0-05` | Every in-scope/deferred capability has a rationale and owner | [Scope matrix](scope-and-feature-matrix.md), [roles](roles-and-signoff.md) | Partial | Assign owners and approve scope |
| `G0-06` | Required solver licences and oracle runtime are available | [Compatibility matrix](compatibility-matrix.md), [Gate 1 runtime evidence](../gate-1/runtime-evidence.json) | Partial | GAMS + full-size SCIP/HiGHS qualified; qualify native full-size CPLEX |
| `G0-07` | HiGHS capability is not overstated | [ADR-0004](../adr/0004-solver-profiles-and-sos.md) | Candidate met | Accept ADR; retain LP-only label |
| `G0-08` | Gate roles include independent validation and market expertise | [Roles and sign-off](roles-and-signoff.md) | **Hold** | Appoint all required roles |
| `G0-09` | Initial tolerance, corpus, discrepancy, and claim policies are approved | [Validation baseline](validation-baseline.md) | Candidate | Validation lead and SME review/signature |
| `G0-10` | TDD claim has immutable evidence and CI design | [ADR-0007](../adr/0007-probity-tdd-evidence.md), [TDD schema](schemas/tdd-evidence.schema.json) | Candidate | Accept ADR/schema and assign CI owner |
| `G0-11` | Architecture, GDX, solver, oracle, evidence, and pricing decisions are recorded | [ADR index](../adr/README.md) | Candidate | Review and accept/reject every proposed ADR |
| `G0-12` | No unresolved source conflict could change first-release economics or claim | Reconciliation, risk, and decision registers | **Hold** | Close or explicitly decide all material open model decisions |

## Deliverable completeness

| Required deliverable | Artifact | Complete as candidate |
|---|---|---|
| Project charter | [Charter](charter.md) | Yes |
| Scope and feature/mode inventory | [Scope matrix](scope-and-feature-matrix.md) | Yes; owners pending |
| Source/checksum manifest | [Source register](source-register.json) | Partial; external hashes pending |
| v15/v5 reconciliation and v16 delta | [Reconciliation](formulation-reconciliation.md) | Draft; clause review pending |
| Compatibility/solver matrix | [Compatibility matrix](compatibility-matrix.md) | Yes; runtimes unqualified |
| Validation/corpus/tolerance policy | [Validation baseline](validation-baseline.md) | Yes; approval pending |
| Licence/provenance register | [Licence register](licence-and-provenance-register.md) | Yes; decisions pending |
| Risk/dependency register | [Risk register](risk-and-dependency-register.md) | Yes |
| Candidate evidence manifest | [Pack manifest](pack-manifest.json) | Yes; decision remains HOLD |
| TDD evidence schema | [JSON Schema](schemas/tdd-evidence.schema.json) | Yes; acceptance pending |
| Gate evidence schema | [JSON Schema](schemas/gate-evidence-manifest.schema.json) | Yes; acceptance pending |
| Role/sign-off matrix | [Roles](roles-and-signoff.md) | Yes; all roles open |
| ADRs | [ADR index](../adr/README.md) | Yes; all proposed |

## Hold rationale

The engineering baseline pack is complete, and Gate 1 research was explicitly
directed on 29 August 2026. Passing the release-governance gate now would make
unsupported claims about legal rights, source reconciliation, solver access,
reviewer independence, and governing-document immutability. The decision is
therefore **HOLD**.

## Decision record

| Field | Entry |
|---|---|
| Decision | Engineering baseline complete; governance HOLD; Gate 1 characterization authorized |
| Material open actions | `G0-01`, `G0-02`, `G0-03`, `G0-05`, `G0-06`, `G0-08`, `G0-09`, `G0-11`, `G0-12` |
| Conditional actions | None; current holds are material |
| Next review | After named roles, legal review, archived hashes, source reconciliation, and native GAMS/CPLEX qualification |
| Signatures | Pending |
