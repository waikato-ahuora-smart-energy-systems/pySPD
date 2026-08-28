# Formulation reconciliation and delta register

| Field | Value |
|---|---|
| Status | Draft — independent market-SME review required |
| Compatibility source | vSPD v5.0.6, commit `21b1cf33f5607399331dcb1c03270348def5ccc8` |
| Governing intent | SPD Model Formulation v15.0 |
| Future delta | SPD Model Formulation v16.0 |

## Reconciliation rule

For the v5 compatibility claim, readable pinned vSPD source is the executable
oracle. SPD Formulation v15 supplies governing intent and terminology. A
difference between them is recorded and resolved; it is never silently
normalized.

This register identifies the required mapping units but is not yet a completed
clause-by-clause SME reconciliation. Gate 0 remains on hold until every
applicable v15 clause has a stable requirement ID, source location,
interpretation, implementation target, test obligation, and reviewer decision.

## Requirement identifier convention

| Prefix | Meaning |
|---|---|
| `V15-*` | Requirement derived from SPD Formulation v15 |
| `V5SRC-*` | Observable behavior derived from pinned v5 source |
| `V16D-*` | Deferred change derived from SPD Formulation v16 |
| `MDR-*` | Approved model decision resolving ambiguity or difference |

## v15-to-v5 reconciliation matrix

| Requirement family | Governing source | Pinned v5 source | Target class | Status | Required closure evidence |
|---|---|---|---|---|---|
| Sets, mappings, and case identity | v15 sets/data definitions | `vSPDmodel.gms`, `vSPDsolve.gms` loading/preprocessing | `CaseData`, preprocessor classes | To verify | Clause/source mapping and schema tests |
| Objective sense and net-benefit terms | v15 objective | `vSPDmodel.gms` objective equations | `ObjectiveComponent` | To verify | Component coefficient and decomposition tests |
| v5 RTD generation-change perturbation | v5 source behavior | `vSPDmodel.gms`/`vSPDsolve.gms` | Named objective contribution | Source-specific | Exact `0.0005` coefficient and activation test |
| v5 reserve-sharing perturbations | v5 source behavior | `vSPDmodel.gms` | Named objective contributions | Source-specific | Exact `1e-5`/`2e-5`/`3e-5` tests |
| Energy offers and bids | v15 offer/bid formulation | `vSPDmodel.gms` | `EnergyMarketComponent` | To verify | Block, capacity, coupling, and objective trace |
| Dispatchable/discrete demand | v15 demand rules | `vSPDmodel.gms` | `DemandBidComponent` | To verify | Continuous/discrete cases and MIP structure |
| Generation-start ramping | v15 ramp formulation | `vSPDmodel.gms`, `vSPDsolve.gms` | `RampingComponent` | To verify | Bound, duration, and soft-violation tests |
| Schedule prior-output fallback | v5 procedural behavior | `vSPDsolve.gms` solve loop | `Vspd506SolvePolicy` | Source-specific | Sequential state-transition characterization |
| Bus energy balance | v15 nodal balance | `vSPDmodel.gms` | `EnergyBalanceComponent` | To verify | Matrix, residual, and price-row mapping |
| AC DC-load flow and angles | v15 AC transmission | `vSPDmodel.gms` | `AcNetworkComponent` | To verify | Topology, reference bus, angle, and flow tests |
| AC capacity/outages | v15 AC limits | `vSPDmodel.gms`, preprocessing | `AcNetworkComponent` | To verify | Direction/outage/boundary tests |
| AC fixed and PWL losses | v15 loss formulation | `vSPDmodel.gms`, `vSPDsolve.gms` | `AcLossComponent` | To verify | Curve, segment, direction, and rental evidence |
| HVDC flow/capacity | v15 HVDC formulation | `vSPDmodel.gms` | `HvdcComponent` | To verify | Direction, pole, round-power, and bound tests |
| HVDC fixed/PWL losses and SOS | v15 HVDC losses | `vSPDmodel.gms` | `HvdcLossComponent` | To verify | Native-SOS matrix and analytic curve tests |
| Circular/nonphysical flow treatment | v15 intent plus source procedure | `vSPDsolve.gms` branch-flow re-solve | `BranchFlowPolicy` | To verify | Detector, transition, fallback, degraded status |
| FIR/SIR reserve offers | v15 reserve formulation | `vSPDmodel.gms` | `ReserveOfferComponent` | To verify | Quantity/cost/capability microcases |
| PLRO/TWRO/ILRO | v15 reserve capability | `vSPDmodel.gms` | `ReserveCapabilityComponent` | To verify | Product and coupling matrix tests |
| Generator/group/manual/DC risks | v15 risk formulation | `vSPDmodel.gms`, preprocessing | `RiskComponent` subclasses | To verify | Binding/nonbinding case per risk family |
| Link and directional-link risk | v15 Link Risk change | `vSPDmodel.gms`, `vSPDsolve.gms` | `LinkRiskComponent` | To verify | 2025 commissioning-risk pack and microcases |
| AC Secondary Risk | v15 Secondary Risk change | `vSPDmodel.gms`, `vSPDsolve.gms` | `SecondaryRiskComponent` | To verify | Risk subtraction/setter/report tests |
| NMIR reserve sharing | v15 NMIR formulation | `vSPDmodel.gms` | `ReserveSharingComponent` | To verify | Factors, zones, binaries, and full-price audit |
| Branch security constraints | v15 branch constraints | `vSPDmodel.gms` | `BranchSecurityComponent` | To verify | LE/GE/EQ and every factor type |
| Market-node constraints | v15 market-node constraints | `vSPDmodel.gms` | `MarketNodeSecurityComponent` | To verify | LE/GE/EQ and every factor type |
| Energy/reserve scarcity | v15 scarcity formulation | `vSPDmodel.gms`, preprocessing | `ScarcityComponent` | To verify | Tranche, threshold, price, and penalty tests |
| Soft violations and penalties | v15 violation variables | `vSPDmodel.gms` | Component-owned slacks + objective terms | To verify | Economic ordering and exact coefficient tests |
| MIP pricing convention | Runtime behavior, not assumed from v15 | ADR-0008 SCIP/HiGHS runtime; CPLEX deferred | `Vspd506PricingEngine` | Characterized for sample | Status `1/1`, fixed-LP matrix, marginals, corpus expansion |
| Node/bus price mapping | v15 post-processing | `vSPDsolve.gms` | `Vspd506PricingEngine` | Verified for final-scenario sample | Sign/allocation exact; full finite-difference corpus pending |
| Dead/disconnected price handling | v5 source; excluded from 2019 audit | `vSPDsolve.gms` | Pricing postprocessor class | New validation | Analytic topology and oracle cases |
| Invalid/SOS1 price replacement | v15/v5 post-processing | `vSPDsolve.gms` | Pricing postprocessor class | To verify | Bad-price and exact-boundary tests |
| Publication-duration weighting | v5 source | `vSPDperiod.gms`, `vSPDsolve.gms` | Publication policy class | To verify | Seconds, zero-duration, and rounding tests |
| Override ordering/effects | v5 source | `vSPDoverrides.gms` | Override preprocessor classes | To verify | One test per override and ordering test |
| Report fields and audit surfaces | v5 source | `vSPDreportSetup.gms`, `vSPDreport.gms` | `Vspd506ResultSchema`, renderer classes | To verify | Field trace and report parity |

## Known source/formulation questions

| ID | Question | Gate impact | Owner |
|---|---|---|---|
| `MDR-OPEN-001` | Which v15 clauses are intentionally approximated or extended by v5 procedural behavior? | G0 hold | Market SME — TBD |
| `MDR-OPEN-002` | Does later native CPLEX cross-validation materially differ from the accepted fixed-discrete HiGHS convention? | Deferred CPLEX claim | Optimization lead — TBD |
| `MDR-OPEN-003` | Which date-compatibility branches are normative for the proposed 2022–2025 window? | G1/G3 | Data lead — TBD |
| `MDR-OPEN-004` | Which official reports/rounding fields form the first release contract? | G0/G9 | Product owner — TBD |

## v16 delta register

| Delta ID | v16 change | v5 compatibility treatment | Future PySPD treatment | Status |
|---|---|---|---|---|
| `V16D-001` | Equal-price offer-block tie-break | Do not backport | Replacement/new component selected by `Spd16Formulation` | Deferred |
| `V16D-002` | Paired-BESS preprocessing and mutually exclusive operating mode | Do not backport | Battery preprocessor/component and discrete pricing audit | Deferred |
| `V16D-003` | Reserve-price fallback when island cleared reserve is zero | Do not backport | `Spd16PricingEngine` policy | Deferred |
| `V16D-004` | Minor formulation/software clarifications | Evaluate individually | Clause-level delta and impacted-gate analysis | Unclassified pending SME review |

Link Risk and AC Secondary Risk are v15 changes already present in the pinned v5
source; they are not v16 deltas.

## Reconciliation completion test

Gate 0 can pass this artifact only when:

- every applicable v15 clause is represented;
- every row has a stable requirement ID and source anchor;
- differences have an approved model decision;
- every requirement has a target class and planned test/oracle evidence;
- deferred clauses match the signed scope matrix; and
- the market SME and validation lead sign the register.
