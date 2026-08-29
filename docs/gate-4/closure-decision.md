# Gate 4 closure decision

## Decision

Gate 4 is **closed — pass for the qualified macOS arm64/HiGHS profile** on 29
August 2026. Stage 5, the AC network, losses, and security-constraint stage, is
authorized for that profile.

No independent reviewer or approval is required under project direction. The
implementation agent performed the recorded validation, consistent with
ADR-0009.

## Basis

- Commit `b2a023c` implements the immutable class-based core-energy components,
  normalized data contract, solver/pricing/result extensions, canonical matrix
  exporter, and independent validator.
- Commit `b798b28` retains vSPD reporting auxiliaries and explicit scarcity,
  extends the preprocessing projection, and implements exact Gate 1 Stage 4
  matrix and full-case price qualification tools.
- Commit `7a1bc60` binds all changed Gate 4 production paths to Probity red/green
  evidence.
- The GAMS and Pyomo Stage 4 projections have identical logical and structural
  SHA-256 over all row/column identities, row bounds, variable bounds,
  integrality, objective coefficients, and 12,892 nonzero coefficients.
- The representative RTD projection solves optimally with qualified HiGHS;
  independent objective/residual checks pass and dual prices match complete
  load-perturbation solves within the governed tolerance.
- Nineteen focused tests cover all required analytic, coefficient/bound,
  complementarity, finite-difference, repeat-build, immutability, and extension
  behaviors. The full repository suite, lint, typing, and Probity audit pass.

## Limitations that do not block this qualified Gate 4 decision

- Native CPLEX cross-validation remains deferred by the binding ADR-0008 project
  decision. No claim of CPLEX parity, CPLEX dual reproduction, or CPLEX support
  is made. Optimal GAMS SCIP/fixed-HiGHS oracle evidence and optimal Pyomo HiGHS
  are the approved current pathway.
- Linux x86_64 execution remains explicitly deferred by ADR-0011. No Linux
  compatibility, solver, portability, or release claim is made.
- The Gate 4 balance is an independent per-island vertical slice. Stage 5 owns
  bus allocation, AC flow, losses, bus slacks, and nodal price separation.
- Joint-batch solving is not enabled, so its conditional criterion is not
  applicable.
- Reserve, HVDC, integer/SOS, scarcity-reserve, and solved shortfall feedback
  remain owned by later stages.

## Residual blockers

None for the declared Gate 4 scope and qualified platform.
