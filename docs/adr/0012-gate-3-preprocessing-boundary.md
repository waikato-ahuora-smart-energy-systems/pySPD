# ADR-0012: deterministic preprocessing boundary for vSPD 5.0.6

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 29 August 2026 |
| Deciders | Project direction and implementation agent |

## Context

The vSPD `vSPDsolve.gms` program mixes input compatibility, static model-data
derivation, solve-loop initialization, and post-solve feedback. A Pyomo port
needs a stable boundary that is modular, testable without a solver, and faithful
to the pinned vSPD v5.0.6 behavior.

## Decision

`Vspd506Preprocessor` is the formulation-specific class facade. It composes pure
`PreprocessingStep` classes through a dependency-ordered pipeline and returns
immutable sparse artifacts plus a logical hash for every named checkpoint.
Inputs remain immutable `CaseData`; transformations never mutate canonical GDX
records.

The static pipeline includes compatibility, topology, loss curves,
offers/bids/load, and constraints/risk/scarcity. First-RTD load reconstruction is
an explicit settings-controlled pure branch. The solve-feedback-dependent
mapped-node transfer rule is a separate pure `ShortfallTransferResolver`; later
solve policies may invoke it without reimplementing its economics.

Override application is a separate ordered transformation. Every matched
change records target, key, method, operand, precedence, before, and after.

Sparse absent and explicitly stored zero are normalized only by the oracle
comparator, where GAMS parameter storage makes them economically equivalent.
The canonical input boundary continues to preserve their distinction.

## Consequences

- Steps can be replaced or extended through declared dependencies without
  subclassing a monolithic model builder.
- Structural signatures detect changes in step classes, dependencies, outputs,
  or settings.
- RTD feedback remains usable as a pure function while its repeated solve-loop
  orchestration is owned by later solve stages.
- Gate 1's neutrality-qualified GAMS checkpoint is reused as the Gate 3 oracle.
- Linux x86_64 remains deferred by ADR-0011 and has no Gate 3 support claim.

## Rejected alternatives

- Executing GAMS preprocessing at normal Python runtime would retain the legacy
  runtime dependency and prevent independent Pyomo operation.
- Embedding preprocessing inside Pyomo component construction would obscure
  checkpoint parity and couple data derivation to solver-facing algebra.
- Re-instrumenting a new oracle was rejected because Gate 1 already produced a
  hash-bound, observationally neutral preprocessing checkpoint.
