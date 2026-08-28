# Risk and external-dependency register

| Field | Value |
|---|---|
| Status | Open |
| Review cadence | Every gate and after any baseline/source change |

Likelihood and impact use `Low`, `Medium`, `High`, or `Critical`. Owners are
roles until named people are appointed.

## Risks

| ID | Risk | Likelihood | Impact | Primary controls | Owner | Gate state |
|---|---|---|---|---|---|---|
| `R-001` | Public vSPD v5 lags current SPD v16 | Certain | Critical | Explicit formulation classes, v5/v16 delta register, effective-date compatibility | Sponsor/SME | Controlled by scope; monitor |
| `R-002` | v15 intent and v5 behavior differ materially | Medium | High | Clause/source reconciliation and model decisions | Market SME | **G0 hold** |
| `R-003` | Source/data/specification rights prohibit intended distribution | Medium | Critical | Legal review, fetch-by-hash, attribution, no premature redistribution | Legal reviewer | **G0 hold** |
| `R-004` | Native GAMS/CPLEX oracle cannot be licensed or reproduced | Medium | Critical | GAMS/SCIP/HiGHS characterization is operational; secure CPLEX link and immutable oracle artifacts | Sponsor/technical lead | **G0/G1 hold** |
| `R-005` | MIP price convention is assumed incorrectly | Medium | Critical | Gate 1 runtime/effective-option characterization, separate snapshots | Optimization lead | G1 hold |
| `R-006` | GDX ordering/sparse/special values are lost | Medium | Critical | Explicit logical encoding, cross-reader and round-trip tests | Data lead | G2 |
| `R-007` | Historical schema/date branches are missed | Medium | High | Versioned schemas, boundary corpus, preprocessing checkpoints | Data lead | G1/G3 |
| `R-008` | HiGHS is misrepresented as full-model capable | Medium | High | LP-only profile; named SOS reformulations and Gates 6/7 | Technical lead | Controlled by ADR |
| `R-009` | Solver degeneracy is mistaken for a defect or used to hide one | High | High | Common optimum target/ranges, KKT, independent classification | Validation lead | G1/G9 |
| `R-010` | Persistent solver state leaks coefficients, fixings, primals, or duals | Medium | Critical | Structural signatures, rebuild policy, fresh-build parity, stale-state tests | Technical lead | G9 |
| `R-011` | Branch-flow fallback publishes degraded economics silently | Low | Critical | Typed degraded state, result/report manifest, release failure by default | Technical lead | G6/G7/G8 |
| `R-012` | Daily data completeness is mistaken for case-type completeness | Medium | High | Signed case-type matrix and separate corpus per type | Validation lead | G0/G9 |
| `R-013` | Golden outputs are regenerated from PySPD defects | Medium | Critical | Oracle-only goldens, separate review, hashes, CI baseline protection | Validation lead | G1 onward |
| `R-014` | Probity hook is treated as complete TDD proof | Medium | High | Immutable red/green schema and CI enforcement | Release owner | G2 |
| `R-015` | Class architecture becomes a monolith or circular plugin graph | Medium | High | ABC contracts, ownership/dependency validation, extension tests | Technical lead | G2/G4 |
| `R-016` | Full-corpus qualification is too slow and gets skipped | Medium | High | Tiered CI, immutable cache, isolated parallelism, release gate remains mandatory | Release owner | G9 |
| `R-017` | Independent assurance begins too late | Medium | High | Appoint validation lead at G0 and review evidence every gate | Sponsor | **G0 hold** |
| `R-018` | Scope expands to DPS/DWH/FTR/Pivot before baseline parity | Medium | High | Signed scope matrix and formal change control | Sponsor | Controlled; monitor |

## External dependencies

| ID | Dependency | Required by | Current state | Closure evidence | Owner |
|---|---|---|---|---|---|
| `D-001` | Named sponsor and gate authority | G0 | Unassigned | Signed roles record | Sponsor organization |
| `D-002` | NZ market SME | G0 | Unassigned | Signed v15/v5 reconciliation | Sponsor |
| `D-003` | Independent validation lead | G0 | Unassigned | Appointment and independence declaration | Sponsor |
| `D-004` | Legal/licensing reviewer | G0 | Unassigned | Signed licence register | Sponsor |
| `D-005` | GAMS runtime/licence | G0/G1 | GAMS 54.3.1 installed outside `PATH`; full-size SCIP/HiGHS executed | [Gate 1 runtime evidence](../gate-1/runtime-evidence.json) | Technical lead |
| `D-006` | Native GAMS CPLEX runtime/licence | G0/G1 | Link present but size-limited; GAMSPy entitlement is not transferable | Version/licence/options manifest and full-size price run | Technical lead |
| `D-007` | v15/v16/licence/audit PDF archive | G0 | URLs known; hashes/storage pending | Immutable URI, size, SHA-256 | Data steward |
| `D-008` | Daily Pricing GDX access | G1 | Public source identified; corpus not fetched | Per-file manifest and representative fetch | Data steward |
| `D-009` | 2023/2025 historical packs | G1 | Git commits identified; rights/applicability pending | Hashes, legal decision, profile mapping | Validation lead |
| `D-010` | Gate evidence storage | G0/G1 | Not selected | Immutable retention service and access policy | Release owner |
| `D-011` | Linux x86_64 CI | G2 | Not configured | Clean `uv sync --frozen` and test run | Release owner |
| `D-012` | Pyomo/solver package versions | G2 | Not selected | ADR update and `uv.lock` | Technical lead |

## Escalation

- Critical residual risk blocks the relevant gate.
- A High risk may receive a conditional action only when it cannot change
  formulation, feasibility, prices, legal rights, or the release claim.
- Repeated source, runtime, or schema unavailability triggers sponsor review of
  scope and schedule; it does not justify inventing reference behavior.
- Every accepted risk states who accepts it, evidence considered, expiry, and
  affected claim.
