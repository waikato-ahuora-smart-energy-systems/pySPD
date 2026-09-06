# Gate 6 — HVDC, discrete solving, and fixed-MIP pricing

| Field | Value |
|---|---|
| Gate | G6 — Submodel solve and pricing foundation equivalent |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Current decision | **CLOSED — PASS FOR QUALIFIED MACOS ARM64/GAMS-SCIP/HIGHS PROFILE** |
| Gate 5 dependency | Closed by commit `5815b64` |
| Implementation | `098ecd4` |
| Probity evidence | `cfddf4c` plus corrected final record |
| Primary MIP | SCIP through licensed GAMS 54; optimum and incumbent required |
| Pricing RMIP | Fix every discrete decision, remove discrete/SOS domains, solve with HiGHS 1.15.1 |
| Oracle | Pinned vSPD 5.0.6 semantic Convert matrix/dictionary |
| CPLEX | Deferred by ADR-0008; no CPLEX runtime claim |
| Linux | Deferred by ADR-0011; no Linux claim |

Gate 6 adds immutable HVDC data, modular flow/loss/lambda and security
components, native and portable SOS2 representations, discrete-demand and flow-
direction decisions, nonphysical-flow detection, capability-aware GAMS-SCIP
MIP outcomes, immutable primary/pricing snapshots, and an explicit fixed-MIP to
HiGHS-RMIP pricing state machine.

The continuous Pyomo and GAMS HVDC projections are exactly identical: 16 rows,
36 columns, 88 nonzeros, matching logical and structural SHA-256 values, and no
identity, bound, objective, integrality, or coefficient mismatch. The pinned
923-bus case solves optimally and passes every independent HVDC identity with a
maximum residual of `2.84e-14`; all 523 node prices are finite and the rebuilt
load perturbation differs from its nodal dual by only `2.27e-5` NZD/MWh.

The representative case does not require a MIP transition. Dedicated analytic
cases therefore exercise real licensed SCIP solves for portable SOS2, discrete
demand, and automatic nonadjacent-loss fallback. They then fix all accepted
discrete decisions in a separate rebuilt model and solve the continuous RMIP
with HiGHS. The audited four-discrete example leaves zero discrete variables and
zero SOS constraints in pricing, preserves an identical algebra fingerprint,
and matches a fixed-MIP finite-difference price within `1e-9` NZD/MWh.

See the [source map](source-map.md), [matrix evidence](oracle-matrix-parity.json),
[solve/price evidence](solve-price-validation.json), [SOS/RMIP evidence](sos-rmip-evidence.json),
[checklist](gate-checklist.md), and [closure decision](closure-decision.md).
Gate 6 is closed and Gate 7 is authorized for the same qualified profile.
