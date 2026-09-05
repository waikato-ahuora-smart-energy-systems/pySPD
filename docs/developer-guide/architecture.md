# Architecture

PySPD separates source handling, preprocessing, algebra, solve policy, pricing,
orchestration, validation, and reporting. The composition root is
`PyspdApplication`.

```text
GDX
 └─ GdxAdapter / LegacyV3InputAdapter
     └─ SymbolCatalog validation
         └─ DailyCaseSelector + DailyCaseDataIndex
             └─ DailyCasePreparer / versioned preprocessor
                 └─ ModelAssembler(Formulation)
                     ├─ ModelComponent classes
                     ├─ SolvePolicy: MIP → fixed RMIP
                     ├─ PricingEngine
                     └─ independent validators
                         └─ DailyRunner / publication
                             └─ ReportBundle + manifest
```

## Core contracts

`RawSymbols` preserves the GDX boundary without silently coercing GAMS special
values. `CaseData` binds one exact case identity to an isolated source view.
Preprocessing returns immutable typed inputs such as `ReserveCase`.

`Formulation` declares component classes, preprocessors, solve policy, pricing
engine, result schema, and report renderer. `ModelAssembler` resolves component
dependencies through named `ModelArtifacts`, rejects duplicate ownership, and
seals the registry after construction.

## Component areas

- `core_energy`: offers, bids, scarcity, ramping, balance and economics;
- `network`: AC topology, flows, losses, constraints and node pricing;
- `hvdc`: HVDC energy transfer, losses, SOS state and pricing solve policy;
- `reserve`: FIR/SIR offers, requirements, risks, sharing, scarcity and price
  intervals;
- `v16`: version-specific data, components, pricing and validation;
- `orchestration`: selection, audited overrides, shortfall loops, publication
  and parallel execution; and
- `reporting`: deterministic typed tables and hash-bound bundles.

## Solve state machine

The normal reserve formulation:

1. assembles the full Pyomo model;
2. solves the MIP with native SCIP SOS2 support;
3. records every discrete and SOS member value;
4. clones the solved model;
5. fixes discrete/SOS state and relaxes the pricing model;
6. solves the RMIP with HiGHS;
7. applies tightly bounded canonicalization only where governed;
8. calculates raw/repaired/node/reserve prices; and
9. runs bounded shortfall and publication logic.

The primary and pricing models remain distinct evidence objects in a serial
diagnostic. A production multi-process parent receives portable values and
pre-rendered rows, never a live Pyomo graph.

## Parallel execution

`GenerationStartBoundaryClassifier` proves whether a case can start without
predecessor generation. `DynamicCaseJobPlanner` makes canonical one-case jobs.
`ProcessShardCoordinator` uses the portable `spawn` context, keeps at most one
job per worker in flight, attributes failures, and returns results in source
order.

Worker-local source/index caches avoid rereading the GDX for every job.
Unordered reserve domains are sorted before Pyomo construction so Python hash
seeds cannot change constraint identities.

## Why periods are not one vectorized model

Current vSPD pricing cases are largely separable. A qualified two-period model
was materially slower despite matching objective and primal physics. Independent
processes therefore provide better throughput and isolation. Genuine storage,
commitment, or energy-budget coupling would justify a new multi-period
formulation with explicit state-transition equations.
