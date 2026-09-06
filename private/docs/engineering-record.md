# Engineering record

The engineering record preserves how PySPD's compatibility claims were defined,
implemented, tested, and amended. It is an audit trail, not the recommended
starting point for running the software.

## Where to look

| Question | Record |
|---|---|
| What is PySPD intended to reproduce? | [Project charter](gate-0/charter.md) |
| Which inputs, outputs, solvers, and platforms are in scope? | [Compatibility matrix](gate-0/compatibility-matrix.md) |
| Why was a technical approach selected? | [Architecture decision records](adr/README.md) |
| What are the full stage definitions and gates? | [Stage-and-gate plan](pyomo-vspd-stage-gate-plan.md) |
| What is the current end-to-end parity evidence? | [Gate 12 record](gate-12/README.md) |
| What remains for the paper-replication study? | [Stage 13 record](gate-13/README.md) |
| What prevents public distribution? | [Licence and provenance register](gate-0/licence-and-provenance-register.md) |

## How the record is organized

Each completed engineering gate can contain:

- a checklist and closure decision;
- a source-to-implementation map;
- canonical matrix, solver, and report evidence;
- red/green Probity TDD records; and
- environment, source, configuration, and artifact hashes.

The numbered gate directories are retained so a later result can be traced to
the decision and evidence boundary in force when it was produced. They are retained only in this private repository folder. User documentation
is published separately from `docs/`.

## Gate index

Use each gate's own status, checklist, and closure decision when interpreting
its evidence. A directory's presence does not imply that the gate is closed.

| Record | Area |
|---|---|
| [Gate 0](gate-0/README.md) | Baseline, scope, and governance |
| [Gate 1](gate-1/README.md) | Reference characterization |
| [Gate 2](gate-2/README.md) | Canonical data boundary |
| [Gate 3](gate-3/README.md) | Versioned preprocessing |
| [Gate 4](gate-4/README.md) | Core energy formulation |
| [Gate 5](gate-5/README.md) | AC network |
| [Gate 6](gate-6/README.md) | HVDC and pricing solve boundary |
| [Gate 7](gate-7/README.md) | Reserve formulation |
| [Gate 8](gate-8/README.md) | Daily orchestration |
| [Gate 9](gate-9/README.md) | Reports and application integration |
| [Gate 10](gate-10/README.md) | Packaging and release qualification |
| [Gate 11](gate-11/README.md) | Formulation-version extension |
| [Gate 12](gate-12/README.md) | End-to-end historical parity |
| [Stage 13](gate-13/README.md) | Residential-PV paper-replication plan |
| [Research record](gate-research/README.md) | Separate analytic research profiles |

## Reading validation claims

Treat each claim as scoped by formulation, input schema, date population,
solver profile, report surface, platform, and numerical convention. Later
evidence can strengthen or amend an earlier gate without erasing its historical
record.

The user-facing summary is [current limitations](../../docs/reference/limitations.md). The
controlling technical interpretation is [interpreting parity](../../docs/validation/interpreting-parity.md).
