# Gate 7 closure decision

## Decision

Gate 7 is **closed — pass for the qualified macOS arm64/GAMS-SCIP/HiGHS
profile** on 29 August 2026. The mathematical energy/reserve formulation and
its approved pricing path are complete for this profile. Stage 8 daily
orchestration, overrides, and market post-processing is authorized.

No independent reviewer or approval is required under project direction. The
implementation agent performed and recorded the validation under ADR-0009.

## Basis

- Commit `93d098a` implements the immutable reserve data contract, modular
  class-based components, full risk/scarcity/NMIR formulation, reserve-aware
  security and economics, independent validator, energy/reserve pricing, and
  canonical qualification tools.
- The pinned GAMS and Pyomo Gate 7 projections have identical hashes over
  15,381 columns and 1,403 rows, with every discrepancy counter zero.
- The full portable model reaches an optimum with licensed GAMS-SCIP. All 124
  discrete decisions are fixed and all discrete domains relaxed before the
  separately rebuilt HiGHS RMIP is solved.
- Primary physical results and pricing duals remain in distinct immutable
  snapshots. The algebra hash is unchanged, the state hashes differ, and the
  pricing model contains zero discrete variables and zero SOS components.
- Independent recomputation passes 1,211 energy, HVDC, reserve, risk, cover,
  sharing, NMIR, scarcity, and economic identities.
- Rebuilt energy-load and reserve-availability perturbations validate both
  price conventions within their declared tolerances.
- Focused tests, the full 213-test repository suite, lint, typing, evidence
  assertions, and the fail-closed Probity audit pass.

## Qualified limitations

- Native CPLEX and `solvefinal` remain deferred by ADR-0008. No CPLEX runtime,
  basis, or price-equivalence claim is made.
- Linux x86_64 remains deferred by ADR-0011. No Linux execution claim is made.
- The Pyomo GAMS writer rejects native `SOSConstraint`; the qualified runtime
  therefore uses the tested portable binary SOS2 encoding. The canonical
  projection excludes only this equivalent encoding layer.
- The representative case does not activate every optional risk row. Analytic
  tests cover all risk classes and optional secondary domains; inactive
  directional/commissioning inputs are explicitly classified in the source
  map.

## Residual blockers

None for Gate 7 and the declared qualified profile.
