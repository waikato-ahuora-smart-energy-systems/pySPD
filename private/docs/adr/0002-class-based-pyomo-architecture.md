# ADR-0002: class-based Pyomo architecture

| Field | Value |
|---|---|
| Status | Accepted by explicit project direction |
| Date | 28 August 2026 |
| Deciders | Project direction; technical implementation agent |

## Context

vSPD combines data loading, procedural preprocessing, several LP/MIP/SOS model
variants, bounded re-solves, pricing, post-processing, and reports. A literal
translation or one monolithic Pyomo class would be difficult to validate,
extend, profile, and version safely.

The user requires a class-based implementation that is modular and easily
extensible. Pyomo performance also argues against creating a Python object for
every indexed equation or record.

## Decision

Use composition around a standard Pyomo `ConcreteModel` with these abstract
class contracts:

```text
Formulation
ModelComponent
PreprocessorStep
SolvePolicy
SolverBackend
PricingEngine
ResultSchema
ReportRenderer
```

`ModelAssembler` resolves explicit component dependencies, construction order,
shared ownership, and objective contributions and returns an immutable
`BuiltModel` containing the model, artifact registry, formulation, and semantic
structural signature.

Rules:

- each cohesive model subsystem is one concrete `ModelComponent` owning a named
  Pyomo Block;
- one provider owns each shared set, variable, expression, constraint, result
  field, and report field;
- consumers use typed artifact handles, never string searches;
- dependency cycles, duplicate ownership, missing providers, and mutation of
  prior Blocks or `CaseData` are construction errors;
- formulation classes choose component, preprocessing, solve, pricing, result,
  and renderer classes through dependency injection;
- builders do not solve, report, perform I/O, or mutate source data;
- I/O modules do not import Pyomo; and
- class boundaries are subsystem-level while indexed Pyomo objects remain
  sparse data/model structures.

## Consequences

- New formulations can replace a bounded class set without editing unrelated
  v5 code.
- Class and dependency contracts add initial scaffolding and tests.
- Stable component ownership enables matrix/price/report traceability.
- Performance remains compatible with sparse Pyomo construction.

## Rejected alternatives

- **One `ConcreteModel` subclass:** monolithic, tightly coupled, difficult to
  substitute or independently test.
- **Only free builder functions:** insufficient ownership and extension
  contracts for this project.
- **Class per equation/index:** excessive object overhead and fragmented algebra.
- **Global plugin registry:** hidden state and nondeterministic construction.

## Verification

- Gate 2 tests missing/cyclic dependencies, duplicate ownership, deterministic
  selection, immutable inputs, and version-consistent policy/renderer selection.
- Gate 4 tests a synthetic component/policy/schema/renderer extension without
  changing `ModelAssembler` or unrelated classes.
- Structural fingerprints are deterministic across repeated builds.
- Gate 11 proves a v16 replacement does not introduce version conditionals in
  unrelated v5 components/renderers.

## Revisit triggers

- Measured construction/memory cost shows the class boundary itself is material.
- Pyomo introduces a stable component architecture that replaces project-owned
  contracts without losing traceability.
- A new formulation requires a dependency relationship the current DAG cannot
  represent.
