# PySPD documentation

PySPD is a class-based Pyomo implementation of New Zealand's Scheduling,
Pricing, and Dispatch model. It reads vSPD GDX inputs, solves each pricing case
with an explicitly selected solver profile, reconstructs market prices, and
writes deterministic CSV reports with a hash-bound manifest.

The qualified portable pathway is:

```text
SCIP MIP → fix discrete and SOS state → HiGHS RMIP → validated prices/reports
```

PySPD is designed for repeatable model investigation, not as an unqualified
replacement for every historical vSPD execution. The repository's stage-and-
gate evidence records exactly which formulations, dates, outputs, and numerical
conventions have been validated.

## Where to begin

- [Install and run a first case](getting-started.md).
- [Choose a case-study pattern](case-studies/index.md).
- [Review potential case studies to build](case-studies/potential-builds.md).
- [Understand the generated reports](user-guide/results.md).
- [Interpret comparisons with GAMS or CPLEX](validation/interpreting-parity.md).
- [Extend the class-based formulation](developer-guide/extending.md).

## Supported execution surface

| Capability | Current status |
|---|---|
| vSPD 5.x-style daily GDX input | Supported as `vspd-v5.0.6` |
| Legacy 2019 final-pricing GDX input | Supported through `vspd-v3-final-pricing` |
| Reserve co-optimization formulation | `vspd-v5.0.6-reserve` |
| SPD v16 reserve formulation | `spd-v16.0-reserve`, subject to its compatibility window |
| Default solver path | SCIP MIP → HiGHS fixed RMIP |
| Independent alternative pricing path | SCIP MIP → CLP fixed RMIP |
| Parallel independent cases | `worker_count` or `--workers` |
| Historical stress-event atlas | 21 hash-verified CPLEX-backed days |
| Multi-period battery storage | Separate analytic research profile |
| Audited raw-input overrides | Python API; not yet part of the stable CLI schema |
| Inter-period unit commitment | Not implemented |
| Exact CPLEX basis reproduction | Not generally guaranteed |

!!! warning "Validation boundary"

    An optimal solver status establishes optimality for the PySPD algebra. It
    does not by itself establish exact historical-output parity. Degenerate LP
    faces can produce different valid dispatch allocations or dual prices.
    PySPD reports analytical price intervals where they have been independently
    derived; a reference value inside such an interval is accepted without
    rewriting either result.

## Reproducibility principles

Every normal run binds the input SHA-256, application configuration, package
lock, formulation, solver profile, and environment into `manifest.json`.
Reports use stable identities and deterministic ordering. Multi-process runs
restore source order before publishing prices and writing reports.

The detailed engineering record remains available in the [stage-and-gate
plan](pyomo-vspd-stage-gate-plan.md), [ADRs](adr/README.md), and [Gate 12
evidence](gate-12/README.md).
