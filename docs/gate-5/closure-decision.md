# Gate 5 closure decision

## Decision

Gate 5 is **closed — pass for the qualified macOS arm64/HiGHS profile** on 29
August 2026. Stage 6, the HVDC/discrete solve-and-pricing stage, is authorized
for that profile.

No independent reviewer or approval is required under project direction. The
implementation agent performed the recorded validation, consistent with
ADR-0009.

## Basis

- Commit `ed150d3` implements immutable AC-network data, modular Pyomo
  components, optimal-only solve/pricing/result extensions, exact semantic
  matrix tooling, and an independent validator.
- Commit `21cfc61` binds every changed production path to Probity red/green
  evidence and expands the analytic coverage to every required topology,
  direction, loss-boundary, factor, and security-sense class.
- GAMS and Pyomo Stage 5 projections have identical logical and structural
  SHA-256 values over 29,825 rows, 30,084 columns, and 73,953 nonzeros.
- The pinned representative RTD model solves optimally with qualified HiGHS;
  every independent residual passes and the nodal marginal agrees with a
  complete rebuilt perturbed solve.
- The focused Gate 5 suite, full repository suite, lint, typing, and Probity
  audit pass.

## Limitations that do not block this qualified Gate 5 decision

- Native CPLEX remains deferred by ADR-0008. No CPLEX parity, CPLEX dual, or
  native-SOS claim is made.
- Linux x86_64 remains deferred by ADR-0011. No Linux claim is made.
- HVDC variables are deliberately outside Gate 5; their coefficients in bus
  and branch-security equations enter at Gate 6.
- Equality constraints are always active by definition, so a “nonbinding EQ”
  case is not mathematically meaningful. Exact equality and both deficit and
  surplus violation directions are tested instead.
- Reserve, risk, NMIR sharing, reserve scarcity, and full-formulation economics
  remain owned by Gate 7.

## Residual blockers

None for the declared Gate 5 scope and qualified platform.
