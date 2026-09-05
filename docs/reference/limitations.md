# Current limitations

## Validation remains staged

Gate 12 is not closed for the complete historical population. The repository
has strong representative, multi-day and CPLEX-corpus evidence, but users must
not describe all dates, formulations, report fields, or duals as exactly
validated. Consult the [current Gate 12 record](../gate-12/README.md).

## CPLEX basis parity

CPLEX is the designated historical output standard, but exact basis reproduction
is not established for every case. Different optimal supports and LP bases can
change reserve allocation, constraint duals, and zero-flow prices. PySPD accepts
only display-precision equality or independently governed analytical intervals.

## Input schemas

Only the declared v5-style and legacy v3 final-pricing schemas are accepted.
Unknown versions do not receive best-effort parsing. SPD v16 requires a source
date on or after its effective date and does not accept legacy v3 input.

## Case coupling

The production model solves pricing cases independently except for explicit
daily orchestration state such as fallback generation starts and publication.
It does not implement multi-period unit commitment, storage state of charge,
hydro energy budgets, intertemporal demand response, or stochastic coupling.

## Scenario CLI

The stable JSON CLI does not yet contain counterfactual overrides. Audited
overrides are available through the lower-level Python API, and their scenario
definitions need a separate hash record. Production multi-worker execution does
not accept an out-of-band override list.

## Topology and new domains

Scalar branch-capacity changes are supported. Adding/removing branches, nodes,
offers, risks, reserve products or constraint families requires a typed source
transformation or formulation extension and new validation.

## Historical report coverage

The deterministic twelve-table PySPD surface does not recreate every field in
legacy vSPD SystemResults, TraderResults, scarcity, or other aggregate exports.
Historical comparisons must use the governed schema crosswalk.

## GAMS and licenses

Normal solving uses open solver pathways but GDX reading needs a GAMS runtime.
Oracle execution can additionally require GAMS model source and solver-specific
entitlement. A GAMSPy license is not automatically a CPLEX entitlement for an
existing GAMS program.

## Platform qualification

The retained workflow and CI are macOS-focused; Linux x86_64 CI execution was
explicitly deferred. Read the Docs builds documentation on Linux but does not
qualify solver results there.

## Stage 13

The residential-PV paper replication is planned, not complete. Demand-scaling
examples in this guide are generic sensitivity studies and must not be cited as
replicating the paper.
