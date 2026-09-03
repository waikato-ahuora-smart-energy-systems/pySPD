# ADR-0006: pricing convention

| Field | Value |
|---|---|
| Status | Accepted; amended for CPLEX-reference parity on 4 September 2026 |
| Date | 28 August 2026 |
| Deciders | Optimization lead, market SME, validation lead |

## Context

Energy and reserve prices depend on constraint marginals, sign conventions,
units, duration, discrete decisions, solver options, and post-processing. A MIP
does not provide economically meaningful duals in the same way as an LP. The
pinned source options do not by themselves prove whether the qualified runtime
performs a final fixed-discrete LP or which marginals reports consume.

Assuming current CPLEX `solvefinal` defaults or copying a common fixed-MIP recipe
could reproduce neither the historical runtime nor published vSPD behavior.

## Decision

Gate 1 must pin exact runtime versions and all effective options. Under
ADR-0008, the active execution runtime is SCIP MIP followed by an explicit
fixed-discrete HiGHS RMIP. The supplied historical CPLEX result corpus is now
the authoritative correctness oracle. Full CPLEX is licensed through GAMSPy,
but it is not yet integrated as a Pyomo fixed-RMIP backend; the standalone GAMS
Solver Link remains demo-size limited. Gate 1 must demonstrate:

- whether a final continuous model is solved after each relevant MIP;
- the transformation from primary MIP to pricing problem;
- treatment of every integer, semi-discrete, and SOS structure;
- which primary/final primals and marginals feed each report;
- dual signs, reduced costs, units, duration, scaling, and ranged rows; and
- basis/degeneracy sensitivity.

Only after that decision does `Vspd506PricingEngine` implement the convention.
If it is fixed-MIP pricing, PySPD:

1. retains an immutable primary solution;
2. fixes every accepted discrete decision;
3. applies only approved domain/SOS transformations;
4. proves the pricing model is continuous;
5. fingerprints the matrix difference;
6. extracts duals from the pricing LP only; and
7. uses primary primals for physical reports and pricing-LP duals for prices.

LP prices require accepted optimal termination, canonical signs/units, and
finite-difference validation. Price-bearing ranged rows are mapped explicitly.
Historical CPLEX vSPD results are the authoritative price oracle. At the
nondifferentiable zero-flow point of a lossy AC branch, a passive leaf bus uses
the deterministic export-side endpoint as its scalar price. PySPD also emits
the complete analytic interval between the export and load derivatives. For
parent price `p`, receiving-end loss share `r`, inward first-segment factor
`f_in`, and outward first-segment factor `f_out`, the endpoints are:

- `export = p(1-r f_out) / (1+(1-r)f_out)`; and
- `load = p(1+(1-r)f_in) / (1-r f_in)`.

The interval is stored in ascending order so it also remains valid for negative
parent prices. Zero-loss transformer descendants inherit the anchored
interval. Bus intervals are allocated to nodes and publication periods using
the same signed allocation and duration weights as scalar prices. A repair
that changes a bus scalar invalidates its pre-repair interval; a dead-node
price transfer transfers the source interval with the scalar.

The public shape is deliberately minimal: `price` remains the scalar and
`price_interval: [lower, upper]` is present only where an analytic loss-kink
interval exists. It carries no selection-convention or selected-endpoint
field. All differentiable prices remain direct fixed-RMIP marginals and omit
interval metadata. This rule does not change dispatch, the fixed-RMIP
objective, or prices away from the loss kink.

## Consequences

- MIP pricing implementation waits until Gate 1 evidence exists.
- Primary and pricing snapshots must be stored separately.
- Strict historical prices may still require the original solver method and
  basis sequence where CPLEX selected the other endpoint on a degenerate face.
- Passive zero-flow AC-loss leaves use the CPLEX-compatible export endpoint in
  the qualified PySPD path.
- A source-topology-certified price lying between the analytic export and load
  endpoints is dual-equivalent for optimization correctness. It has no effect
  on primal feasibility, dispatch, or objective value. Any difference that
  reaches a node or publication remains a separately reported CPLEX
  output-parity difference.
- Reports expose `price_interval` on affected bus, node, and published-energy
  rows; scalar-only rows contain an empty CSV value.
- Stage 7 repeats the complete pricing audit after NMIR/reserve binaries arrive.

## Rejected alternatives

- **Read “MIP duals”:** not a valid market-pricing convention.
- **Assume `solvefinal=1`:** not proven by the pinned source/runtime yet.
- **Use final-LP primals as dispatch automatically:** may overwrite the accepted
  physical solution.
- **Use one global dual-sign rule:** unsafe across row transformations.

## Verification

- Gate 1 oracle runtime/effective-option evidence and matrix snapshots.
- Analytic sign/unit/complementarity/reduced-cost cases.
- Finite-difference demand and reserve perturbations away from kinks; explicit
  endpoint tests at nondifferentiable zero-flow loss faces.
- Independent recomputation of interval allocation, dead-node transfer, and
  publication weighting.
- Gate 6 submodel and Gate 7 full-formulation pricing-model audits.
- PySPD-to-historical-CPLEX published-output comparison at reference precision,
  with pinned-vSPD comparison retained as secondary diagnostic evidence.

## Revisit triggers

- Gate 1 proves a different convention than the fixed-MIP candidate.
- Solver/runtime upgrades alter final-LP or basis behavior.
- A new formulation changes price-bearing equations or post-processing.
