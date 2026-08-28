# Compatibility matrix

| Field | Value |
|---|---|
| Status | Proposed; SCIP/HiGHS characterization profile executed |
| Observation date | 29 August 2026 |
| Development platform | macOS arm64 |

## Formulation and data profiles

| Profile ID | Formulation/source | Input family | Effective dates | First-release support |
|---|---|---|---|---|
| `audit-v3.0.4` | vSPD v3.0.4 / SPD 11.2 | Exact audit inputs | Historical audit scope | Provenance/assurance only |
| `legacy-v3.1` | vSPD v3.1.0 | Pre-RTP GDX | Through 31 October 2022 | Deferred |
| `rtp-v4` | vSPD v4 | Original post-RTP schema | From 1 November 2022 | Deferred |
| `daily-v5.0.6` | vSPD v5.0.6 | Versioned daily Pricing GDX | Proposed 1 November 2022–21 November 2025 | In |
| `spd-v16` | SPD Formulation v16 | Authoritative v16-compatible data | Effective from approved change date | Gate 11 deferred |

Inputs outside a profile's effective-date/schema contract are rejected. Date
alone never selects a formulation.

## Case-type qualification

| Type | Daily-v5 source availability | Proposed status | Additional evidence |
|---|---|---|---|
| RTD 101 | Primary | In | Full daily corpus and targeted regressions |
| RTDP 201 | Intermittent | In when present | Explicit per-file presence/count manifest |
| PRSS 130 | Primary | In | Full daily corpus and published-price comparisons |
| PRSL 131 | Not established by daily corpus | Deferred | Applicable source/oracle/corpus required |
| NRSS 132 | Not established by daily corpus | Deferred | Applicable source/oracle/corpus required |
| NRSL 133 | Not established by daily corpus | Deferred | Applicable source/oracle/corpus required |
| WDS 120 | Not established by daily corpus | Deferred | Applicable source/oracle/corpus required |

## Python and package profile

| Component | Required | Observed | Status |
|---|---|---|---|
| Python | `>=3.13,<3.14` | `uv` Python 3.13.14 | Candidate |
| `uv` | Locked project workflow | 0.11.29 | Candidate |
| Pyomo | Exact version to be selected in Stage 2 | Not yet a dependency | Pending |
| GAMSPy | Oracle experiment group | 1.27.0 / GAMS API 54.3.1 | Qualified for GAMSPy-native models only |
| Probity | 1.10.0 | 1.10.0 | Available |
| Node | 22.x for Probity tooling | 22.23.2 | Available |
| npm | Lockfile-compatible | 10.9.8 | Available |

Python setup, dependency changes, test commands, and package execution use
`uv`. Direct `pip install` is unsupported.

## Solver profiles

| Profile | Purpose | Required capability | Current workstation | Gate status |
|---|---|---|---|---|
| `gams-cplex-oracle` | Deferred historical/commercial cross-validation | GAMS, CPLEX, GDX, exact options, source overlay | GAMS 54.3.1 installed; native CPLEX link is size-limited | Deferred by ADR-0008 |
| `gams-scip-smoke` | Full-size source/data/objective smoke | Native GAMS, SCIP MIP, HiGHS LP | 15/15 primary MIPs optimal; objectives within `0.0001 NZD` of committed CPLEX | Characterization qualified; no prices |
| `gams-scip-highs-pricing` | Active vSPD execution and pricing reference | SCIP MIP, explicit discrete/SOS fixing, HiGHS RMIP | 15 MIPs + 15 RMIPs optimal; 135 finite node prices; two deterministic runs | Adequate when every required solve is status `1/1`; ADR-0008 |
| `pyomo-cplex-parity` | Deferred strict CPLEX matrix/solution/price parity | LP/MIP/SOS, duals, quality, IIS | CPLEX not detected | Deferred by ADR-0008 |
| `pyomo-highs-lp` | Open LP/default CI | LP/MIP without native reference SOS | HiGHS executable not detected; `highspy` not installed | Stage 2 pending |
| `pyomo-highs-reformulated` | Optional portable full model | Approved binary/incremental SOS replacements | Not implemented | Gates 6/7 deferred |
| `pyomo-gurobi-crosscheck` | Independent commercial check | LP/MIP/SOS, duals, IIS | `gurobi_cl` not detected | Optional pending |

GAMS is installed outside the shell's default `PATH`; the absolute executable
was used for manifested full-size runs. A GAMSPy solver entitlement does not
license the native GAMS CPLEX link, and standard GAMSPy cannot execute the
legacy multi-unit vSPD source unchanged. Under ADR-0008, CPLEX is deferred and
does not block current Gate 1 work; no CPLEX-specific parity claim is permitted.

## SOS capability decision

For the initial profile, HiGHS is **LP/submodel only**. It is not advertised as
a full vSPD solver. A full portable profile requires separately named SOS1/SOS2
reformulations, matrix/economic equivalence, boundary/adjoining-segment tests,
full pricing requalification, and Gate 6 plus Gate 7 approval.

## Platform targets

| Platform | Intended support | Current evidence |
|---|---|---|
| macOS arm64 | Development and portable profiles | `uv`/Python/Node observed; solvers pending |
| Linux x86_64 | CI and release target | No clean-build evidence yet |
| Windows x86_64 | Not first-release target | Deferred unless sponsor adds scope |

Canonical logical-content hashes must remain stable across qualified platforms
even when physical Parquet file hashes differ.

## Runtime acceptance checklist

Each qualified runtime records:

- operating system and architecture;
- Python, Pyomo, solver interface, solver, and licence versions;
- executable/library paths and cryptographic hashes where permitted;
- complete effective options, threads, algorithm, scaling, and tolerances;
- supported capabilities and unsupported outcomes;
- deterministic smoke input/output hashes; and
- `uv.lock` and environment-manifest hashes.
