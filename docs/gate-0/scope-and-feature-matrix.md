# Scope and feature matrix

| Field | Value |
|---|---|
| Status | Proposed for Gate 0 approval |
| First formulation | `vspd-5.0.6` |
| Proposed data window | 1 November 2022 through 21 November 2025 |
| Primary modes | `SPD`, `AUD` |
| Primary data family | Versioned daily `Pricing_YYYYMMDD.gdx` |

## Scope rules

- `In` means required for the first compatibility release and Gate 9 claim.
- `Deferred` means deliberately excluded until a separately gated profile is
  approved.
- `Diagnostic` means usable for assurance but not a supported production API.
- `Unknown` blocks Gate 0 until assigned or deferred.

## Formulation and execution scope

| Capability | Status | First-release requirement | Rationale or condition |
|---|---|---|---|
| vSPD v5.0.6 compatibility | In | Exact pinned commit and configuration profile | First reference baseline |
| SPD Formulation v15 mapping | In | Clause-to-source intent register | Governing context for Link Risk and AC Secondary Risk |
| SPD Formulation v16 | Deferred | New `Spd16Formulation` and Gate 11 | Must not alter v5 results |
| Sequential case/datetime solves | In | Preserve reference order and state | Pinned v5 behavior |
| Joint multi-case solve | Deferred extension | Independence proof and sequential parity | Not reference v5 execution |
| `SPD` mode | In | Reviewed configuration overlay | Standard compatibility runs |
| `AUD` mode | In | Audit surfaces and reports | Assurance evidence |
| `DPS` mode | Deferred | Separate requirements and corpus | Pinned settings default, but outside first release |
| Demand/DWH mode | Deferred | Separate data, scenario, and report profile | Not needed for first compatibility claim |
| FTR mode | Deferred | Source, equations, and fixtures | Referenced paths are incomplete in inspected source |
| Pivot mode | Deferred | Source and fixtures | Referenced paths are incomplete in inspected source |
| Overrides | In | Supported source override families | Required counterfactual behavior |
| Operational SPD replacement | Excluded | None | PySPD is an analysis model, not dispatch infrastructure |
| GUI | Excluded | None | API/CLI first |

## Case-type scope

| Case type | Proposed status | Qualification source |
|---|---|---|
| RTD 101 | In | Daily Pricing GDX plus historical and analytic cases |
| RTDP 201 | In when present | Daily Pricing GDX and explicit presence manifest |
| PRSS 130 | In | Daily Pricing GDX plus published-price evidence |
| PRSL 131 | Deferred pending corpus | Separate applicable input/oracle profile required |
| NRSS 132 | Deferred pending corpus | Separate applicable input/oracle profile required |
| NRSL 133 | Deferred pending corpus | Separate applicable input/oracle profile required |
| WDS 120 | Deferred pending corpus | Separate applicable input/oracle profile required |

Gate 9 may claim only the case types whose rows have an executed, versioned
corpus. Date-complete daily data does not qualify a case type absent from those
files.

## Data and processing scope

| Area | Status | Required behavior |
|---|---|---|
| Consolidated daily schema | In | Versioned by effective date; no fixed symbol-count assumption |
| `i_dateTimeRiskGroupBranch` | In from 17 March 2025 | Conditional presence and domain tests |
| GAMS special values | In | Explicit record presence and EPS/NA/UNDEF/infinity identity |
| GDX-to-canonical conversion | In | Faithful conversion with logical and physical hashes |
| GAMS-free canonical loading | In | Normal runtime does not require GAMS |
| Legacy v3.1 input adapter | Deferred | Separate pre-RTP profile |
| RTP v4 input adapter | Deferred | Separate post-RTP legacy-schema profile |
| Invalid/missing data diagnostics | In | Fail before model construction |

## Mathematical feature inventory

| Feature family | Status | Target component class |
|---|---|---|
| Energy offer and bid blocks | In | `EnergyMarketComponent` |
| Capacity/intermittent limits | In | `EnergyCapacityComponent` |
| Generation-start ramping | In | `RampingComponent` |
| Energy balance and soft violations | In | `EnergyBalanceComponent` |
| AC DC-load-flow and angles | In | `AcNetworkComponent` |
| AC fixed and PWL losses | In | `AcLossComponent` |
| Branch and market-node constraints | In | `SecurityConstraintComponent` |
| HVDC directed flow and capacity | In | `HvdcComponent` |
| HVDC fixed/PWL losses and SOS | In | `HvdcLossComponent` |
| Circular/nonphysical flow handling | In | `BranchFlowPolicy` and `SolvePolicy` |
| FIR/SIR reserve offers | In | `ReserveOfferComponent` |
| PLRO/TWRO/ILRO | In | `ReserveCapabilityComponent` |
| Generator/group/manual/DC risks | In | `RiskComponent` subclasses |
| Link/directional-link risk | In | `LinkRiskComponent` |
| AC Secondary Risk | In | `SecondaryRiskComponent` |
| NMIR reserve sharing and binaries | In | `ReserveSharingComponent` |
| Energy/reserve scarcity | In | `ScarcityComponent` |
| Violation and scarcity penalties | In | `ObjectiveComponent` contributions |
| v5 small objective perturbations | In | Named objective contributions, not called v16 tie-break |
| v16 equal-price tie-break | Deferred | v16 replacement component |
| v16 paired-BESS mode | Deferred | v16 battery component |
| v16 reserve-price fallback | Deferred | v16 pricing policy |

## Solve, pricing, and output scope

| Capability | Status | Acceptance boundary |
|---|---|---|
| SCIP/HiGHS reference solve | In | Active interim Pyomo/reference comparison target under ADR-0008 |
| CPLEX parity solve | Deferred | Later CPLEX-specific comparison profile |
| HiGHS LP solve | In | Portable LP and analytic profile |
| HiGHS full SOS/MIP solve | Deferred until proven | Named reformulations must pass Gates 6 and 7 |
| Gurobi cross-check | Optional | Qualified when licence/runtime is available |
| MIP pricing | In, interim convention characterized | SCIP MIP → fixed-discrete HiGHS RMIP; expand Gate 1 corpus |
| Dead/disconnected price handling | In | Explicitly tested; outside 2019 audit scope |
| Invalid/SOS1 price replacement | In | Branch and date-boundary tests |
| Publication-duration weighting | In | Pinned-vSPD output parity |
| Standard CSV-equivalent reports | In | Versioned `ReportRenderer` classes |
| Audit output surfaces | In | Branch, bus, node, risk, objective, status, and price evidence |
| GDX-equivalent export | In | Subject to legal and data-format decision |

## Change control

Moving a row from `Deferred` or `Excluded` to `In` requires an owner, source,
data contract, oracle, tests, corpus, risk assessment, and impacted-gate rerun.
