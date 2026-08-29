# Gate 6 closure decision

## Decision

Gate 6 is **closed — pass for the qualified macOS arm64/GAMS-SCIP/HiGHS
profile** on 29 August 2026. Stage 7, the coupled reserve/risk/NMIR/scarcity
stage, is authorized for that profile.

No independent reviewer or approval is required under project direction. The
implementation agent performed the recorded validation, consistent with
ADR-0009.

## Basis

- Commit `098ecd4` implements modular HVDC/discrete components, the licensed
  GAMS-SCIP primary-MIP backend, the bounded nonphysical-flow transition, the
  explicit complete-fix HiGHS-RMIP pricing solve, independent validation,
  diagnostics, and canonical matrix tooling.
- Commit `cfddf4c` adds the Probity evidence and committed evidence assertions;
  the final record correction is included with this closure.
- GAMS and Pyomo continuous HVDC projections have identical hashes over 16
  rows, 36 columns, and 88 nonzeros.
- The pinned full AC/HVDC case solves optimally, every independent HVDC check
  passes, and its node-price dual agrees with a rebuilt load perturbation.
- Real licensed SCIP analytic cases prove portable SOS2, discrete bid,
  alternative integer optimum, and automatic enforcement behavior. Every
  pricing run uses a separately rebuilt fixed continuous HiGHS model.
- The focused suite, full repository suite, lint, typing, and Probity audit pass.

## Limitations that do not block this qualified Gate 6 decision

- Native CPLEX and `solvefinal` execution remain deferred by ADR-0008. The
  native SOS2 structure is retained, but no CPLEX runtime or basis-parity claim
  is made.
- Linux x86_64 remains deferred by ADR-0011. No Linux execution claim is made.
- The pinned representative does not contain an active discrete/SOS solve path;
  that path is qualified with transparent analytic cases using the same
  production state machine and real GAMS-SCIP/HiGHS solvers.
- SCIP/HiGHS do not expose IIS through the current adapter. Failed runs retain
  LP/MPS problem copies and explicit raw/normalized termination information.
- Reserve, risk, NMIR sharing, reserve scarcity, and their full-formulation
  pricing requalification remain owned by Gate 7.

## Residual blockers

None for the declared Gate 6 scope and qualified profile.
