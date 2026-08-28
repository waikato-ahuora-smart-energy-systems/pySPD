# PySPD project charter

| Field | Candidate value |
|---|---|
| Charter version | 0.1 |
| Status | Proposed |
| Compatibility baseline | vSPD v5.0.6 at `21b1cf33f5607399331dcb1c03270348def5ccc8` |
| Governing formulation context | SPD Model Formulation v15.0 |
| Future formulation | SPD Model Formulation v16.0, separately versioned |
| Primary implementation | Python 3.13 and Pyomo, managed with `uv` |
| Gate authority | Unassigned |

## Mission

Build a maintainable, class-based Pyomo implementation that reproduces the
declared vSPD v5.0.6 compatibility scope with auditable structural, numerical,
economic, pricing, control-flow, and report evidence.

## Initial release claim

The first release will seek the following claim and no broader one:

> For the declared v5.0.6 source, data, case-type, report, and solver profiles,
> PySPD reproduces the pinned GAMS vSPD reference model's structure, feasible
> economics, solve path, and published-output calculations under the approved
> comparator and discrepancy policies.

Official SPD/market-price comparisons are a secondary validation surface.
PySPD may be called `audited` only if an independent audit explicitly certifies
the named PySPD release and scope.

## Objectives

- Preserve a traceable path from raw GDX records to every model coefficient and
  result.
- Represent the formulation through replaceable `Formulation`,
  `ModelComponent`, `PreprocessorStep`, `SolvePolicy`, `PricingEngine`,
  `ResultSchema`, and `ReportRenderer` classes.
- Reproduce pinned v5 sequential `(case, datetime)` solving, including its
  prior-solution schedule fallback and bounded re-solve behavior.
- Establish matrix, objective-component, residual, pricing, and report parity.
- Support a GAMS-free normal runtime after faithful canonical conversion.
- Provide portable LP capability with HiGHS while retaining CPLEX as the
  normative parity backend.
- Make failure, degradation, degeneracy, and known differences visible.
- Deliver reproducibly from `uv.lock` under auditable red-green-refactor TDD.

## Principles

1. **Version selection is explicit.** Data dates do not silently change the
   formulation class.
2. **Compatibility before modernization.** v5 parity is established before v16
   behavior is introduced.
3. **Composition over a monolith.** One large `ConcreteModel` subclass is
   prohibited; cohesive component classes own named Pyomo Blocks.
4. **Oracle evidence before implementation.** A solving model is not sufficient
   evidence of correctness.
5. **No generic tolerance.** Units, scaling, source precision, and solver
   behavior determine each comparator rule.
6. **No MIP-dual fiction.** Gate 1 must establish the reference pricing
   convention before PySPD implements it.
7. **No silent degraded result.** Fallback solutions with possible circulation
   or nonphysical loss carry a typed degraded status.
8. **No unauditable TDD claim.** Probity is paired with immutable red/green CI
   records.
9. **No direct `pip` workflow.** Python dependencies and commands use `uv`.

## Governance

Stage entry and gate decisions follow the governing plan. Gate 0 requires the
sponsor, technical lead, market SME, validation lead, and legal reviewer. A
person who produced an artifact may explain it but may not be its sole gate
reviewer.

Decision outcomes are `PASS`, `CONDITIONAL PASS`, `HOLD`, or `RESET`. Schedule
pressure cannot waive legal, provenance, formulation, numerical, economic, or
claim criteria.

## Deliverables

- class-based Pyomo package and supported APIs;
- versioned GDX/canonical data contracts;
- solver, pricing, diagnostics, and report adapters;
- complete traceability and test suites;
- immutable oracle, comparison, and gate evidence;
- signed validation and release reports; and
- maintained formulation compatibility and known-difference registers.

## Completion condition

This charter becomes effective only when the required Gate 0 roles sign it and
the [gate checklist](gate-checklist.md) records an authorized decision.
