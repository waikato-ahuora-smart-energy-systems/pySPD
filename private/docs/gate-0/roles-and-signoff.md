# Roles and Gate 0 sign-off

| Field | Value |
|---|---|
| Status | **Unassigned — Gate 0 hold** |
| Independence rule | No artifact is accepted solely by its author |

## Required roles

| Role | Named person | Organization | Accountability | Independence requirement | Status |
|---|---|---|---|---|---|
| Sponsor/product owner | TBD | TBD | Scope, funding, claim, residual risk, final authorization | May not act as sole technical validator | Open |
| Gate authority/chair | TBD | TBD | Agenda, quorum, decision record, conditional actions | Must disclose conflicts | Open |
| Technical/optimization lead | TBD | TBD | Architecture, formulation implementation, solver semantics | Cannot solely accept own implementation | Open |
| NZ electricity-market SME | TBD | TBD | v15/v5 interpretation, units, risks, prices, reports | Independent review of requirement interpretations | Open |
| Data/IO lead and steward | TBD | TBD | GDX fidelity, schemas, corpus, immutable source/data storage | Separate review for own conversions | Open |
| Independent validation lead | TBD | TBD | Corpus, comparator, tolerances, discrepancies, Gate 9 report | Organizationally independent of core implementation | Open |
| Platform/release owner | TBD | TBD | `uv`, CI, TDD ledger, artifacts, SBOM, performance, release | Cannot waive validation failures | Open |
| Legal/licensing reviewer | TBD | TBD | Source/data/spec/solver/distribution rights and notices | Qualified and independent of delivery schedule | Open |
| External reviewer/auditor | TBD | TBD | Later independent reproduction and assurance | Not required to sign G0 but appoint early | Open |

## Gate 0 quorum

Required signatories are:

- sponsor/product owner;
- technical/optimization lead;
- NZ electricity-market SME;
- independent validation lead; and
- legal/licensing reviewer.

The gate authority records the decision. Quorum is not achieved while any
required role is unassigned.

## Independence declarations

Each reviewer records:

1. artifacts authored or materially influenced;
2. reporting line or delivery incentive that could affect independence;
3. solver/vendor or other commercial interest;
4. limitations on competence or review scope; and
5. whether another reviewer is required.

## Approval record

| Role | Decision | Conditions | Name/signature | Date |
|---|---|---|---|---|
| Sponsor/product owner | Pending | — | — | — |
| Technical/optimization lead | Pending | — | — | — |
| NZ electricity-market SME | Pending | — | — | — |
| Independent validation lead | Pending | — | — | — |
| Legal/licensing reviewer | Pending | — | — | — |
| Gate authority/chair | Pending decision record | — | — | — |

Allowed decisions are `Approve`, `Approve with non-material conditions`, or
`Reject`. Conditions that may change formulation, prices, feasibility, legal
rights, scope, or claim are material and require `HOLD`, not conditional pass.

## Current conclusion

Gate 0 cannot pass because no required role or signatory is currently named.
