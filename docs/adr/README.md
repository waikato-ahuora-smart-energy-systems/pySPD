# PySPD architecture decision records

ADRs are immutable after acceptance. A superseding ADR links to the decision it
replaces; accepted history is not rewritten.

| ADR | Decision | Status |
|---|---|---|
| [ADR-0001](0001-formulation-baseline-and-versioning.md) | Pin v5.0.6 and version formulation behavior explicitly | Accepted by project direction |
| [ADR-0002](0002-class-based-pyomo-architecture.md) | Use class-based composition around `ConcreteModel` | Accepted by explicit project direction |
| [ADR-0003](0003-gdx-and-canonical-data-boundary.md) | Separate faithful GDX ingestion from canonical runtime data | Accepted by project direction |
| [ADR-0004](0004-solver-profiles-and-sos.md) | Use CPLEX for parity and restrict HiGHS until SOS evidence passes | Proposed |
| [ADR-0005](0005-oracle-and-evidence-retention.md) | Treat pinned GAMS vSPD as an instrumented, immutable oracle | Proposed |
| [ADR-0006](0006-pricing-convention.md) | Characterize MIP pricing at Gate 1 before implementation | Proposed |
| [ADR-0007](0007-probity-tdd-evidence.md) | Pair Probity with immutable red/green CI evidence | Accepted by explicit project direction |
| [ADR-0008](0008-interim-scip-highs-reference-profile.md) | Treat optimal SCIP MIP + HiGHS fixed RMIP as the active adequate reference; defer CPLEX | Accepted by project direction |
| [ADR-0009](0009-gate-1-review-authority.md) | Gate 1 does not require an independent validation reviewer or approval | Accepted by project direction |
| [ADR-0010](0010-gate-1-date-level-shortfall-qualification.md) | Qualify the shortfall population by 139 hash-bound dates and representative exact fixtures at Gate 1; replay all 546 intervals at Gate 8 | Accepted by project direction |
| [ADR-0011](0011-linux-ci-deferred-after-gate-2.md) | Defer Linux x86_64 execution and restrict Gate 2 qualification to macOS arm64 | Accepted by explicit project direction |
| [ADR-0012](0012-gate-3-preprocessing-boundary.md) | Freeze the Gate 3 preprocessing boundary and oracle checkpoint | Accepted by project direction |
| [ADR-0013](0013-gate-12-shortfall-population-discovery.md) | Discover the 546-case population with recomputed first-loop RTD load and material actual-transfer evidence | Accepted by project direction |
| [ADR-0014](0014-incremental-gate-12-replay-parity.md) | Replay and compare each completed Gate 12 date incrementally | Accepted by project direction |
| [ADR-0015](0015-gate-12-targeted-historical-recovery.md) | Recover named pathological discovery cases without widening the general oracle | Accepted for bounded Gate 12 recovery evidence |
| [ADR-0016](0016-gate-12-residue-only-loop-guard.md) | Skip historical transfer loops only when no material evidence can be emitted | Accepted for bounded Gate 12 discovery evidence |
| [ADR-0017](0017-portable-report-equivalence.md) | Govern SCIP/HiGHS report equivalence separately from strict solver identity | Accepted by project direction for the portable Gate 12 profile |
| [ADR-0018](0018-portable-published-price-report-tolerance.md) | Apply the portable price tolerance to published report rows | Accepted by project direction for the portable Gate 12 profile |
| [ADR-0019](0019-native-scip-sos2-application-state.md) | Use native SOS2 state in the SCIP application solve | Accepted for the SCIP/HiGHS Gate 12 profile |
| [ADR-0020](0020-binding-market-node-dual-allocation.md) | Certify aggregate-preserving dual allocation across one binding market-node limit family | Accepted for the SCIP/HiGHS Gate 12 report profile |

## Status values

- `Proposed`: awaiting the required gate reviewers.
- `Accepted`: approved and binding.
- `Rejected`: reviewed and not adopted.
- `Superseded`: replaced by a linked later ADR.
- `Deprecated`: retained for history but no longer applicable.

## Required ADR fields

Every ADR states context, decision, consequences, rejected alternatives,
verification, and revisit triggers. Gate 0 cannot pass while a release-critical
ADR remains merely proposed.
