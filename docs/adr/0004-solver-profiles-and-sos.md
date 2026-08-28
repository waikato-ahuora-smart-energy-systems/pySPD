# ADR-0004: solver profiles and SOS handling

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 28 August 2026 |
| Deciders | Technical lead, optimization lead, validation lead |

## Context

Pinned vSPD uses GAMS + CPLEX and native SOS1/SOS2 structures. Strict structural,
basis-sensitive, and pricing investigations require a matched CPLEX profile.
HiGHS provides an attractive open solver but the qualified Pyomo interface does
not directly support the reference SOS constraints.

## Decision

Define capability-scoped profiles:

| Profile | Decision |
|---|---|
| `gams-cplex-oracle` | Normative reference; exact runtime/options qualified at Gate 1 |
| `pyomo-cplex-parity` | Normative PySPD compatibility profile |
| `pyomo-highs-lp` | Open LP/submodel and CI profile |
| `pyomo-highs-reformulated` | Disabled until named SOS reformulations pass Gates 6 and 7 |
| `pyomo-gurobi-crosscheck` | Optional independent commercial profile |

All solver code sits behind `SolverBackend`. A result retains raw status and a
capability-aware normalized state; solvers are not forced into false status
identity. Solutions load only after accepted termination checks.

For HiGHS, any full-model path must use separately named binary/incremental
SOS1/SOS2 formulations while CPLEX retains native SOS for parity. The
reformulation is part of the formulation/model manifest, not an invisible
backend rewrite.

Golden/reference profiles pin solver version, interface, effective options,
algorithm, threads, seeds, presolve, scaling, tolerances, and licence state.

## Consequences

- CPLEX access is a Gate 0 dependency for the intended compatibility claim.
- Open CI can begin with LP components before the full discrete model.
- A portable full-model profile is possible but requires substantial separate
  evidence.
- Cross-solver equality focuses on economic invariants where bases/optima differ.

## Rejected alternatives

- **HiGHS as an immediate universal default:** overstates SOS capability.
- **Automatically linearize SOS inside the backend:** hides changed structure.
- **Require identical raw status names:** ignores legitimate solver capability
  differences.
- **Use only one solver:** weakens independent cross-checks and portability.

## Verification

- Gate 2 covers executable/version/options/status/safe-load contracts for LP.
- Gate 6 proves energy/HVDC SOS formulation equivalence and pricing impact.
- Gate 7 repeats every affected audit with reserve/NMIR binaries active.
- Gate 9 compares persistent/warm paths to fresh builds and checks stale state.

## Revisit triggers

- Pyomo/HiGHS gains qualified native SOS support.
- CPLEX licensing or runtime availability changes.
- A new formulation adds unsupported variable/constraint types.
