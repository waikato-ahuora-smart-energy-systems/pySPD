# Gate 4 vSPD v5.0.6 core-algebra source map

The executable authority is the pinned vSPD `Programs/vSPDmodel.gms` and
`Programs/vSPDsolve.gms`. Gate 1's semantic Convert dictionary supplies stable
family and index names; its matrix GDX supplies bounds, objective terms, and
coefficients.

| vSPD family/source behavior | Python owner | Stable model/artifact names | Validation |
|---|---|---|---|
| `GenerationOfferDefintion`; generation/block bounds | `EnergyOffersComponent` | `EnergyOffers.Generation`, `GenerationBlock`, `GenerationOfferDefinition`; `generation*` artifacts | Merit order, capacity, hand matrix, exact GAMS projection |
| `DemBidDefintion`; signed positive/negative block bounds | `DemandBidsComponent` | `DemandBids.Purchase`, `PurchaseBlock`, `DemandBidDefinition`; `purchase*` artifacts | Price-sensitive and negative-bid tests |
| `EnergyScarcityDefinition`; 20 hard-coded vSPD blocks; national/node precedence | `ConstraintRiskStep`, `EnergyScarcityComponent` | `EnergyScarcity.EnergyScarcityBlock`, `EnergyScarcityNode`, `EnergyScarcityDefinition` | Scarcity microcase; exact 10,460-column GAMS projection |
| `GenerationChangeUpDown` | `GenerationRampingComponent` | `GenerationRamping.GenerationUpDelta`, `GenerationDownDelta`, `GenerationChange` | RTD movement and objective decomposition |
| `GenerationRampUp`, `GenerationRampDown`; interval/60 conversion; primary/secondary coupling | `GenerationRampingComponent` | `DeficitRampRate`, `SurplusRampRate`, `RampUp`, `RampDown` | Ramp-up/down, conflicting cap/slack, primary-secondary test, residual evaluator |
| Projected single-island supply/load balance with scarcity and explicit deficit/surplus | `EnergyBalanceComponent` | `EnergyBalance.Balance`, `DeficitGeneration`, `SurplusGeneration` | Hand infeasibility/slack cases, independent residuals, finite differences |
| `SystemCostDefinition`, `SystemBenefitDefinition` | `CoreEconomicsComponent` | `Economics.SystemCostByPeriod`, `SystemBenefitByPeriod` and definition rows | Independent offer-cost and bid-benefit recomputation; exact matrix |
| `SystemPenaltyCostDefinition`, `TotalViolationCostDefinition` | `CoreEconomicsComponent` | `SystemPenaltyByPeriod`, `TotalPenaltyCost` and definition rows | Independent balance/ramp/movement decomposition; exact matrix |
| `TotalScarcityCostDefinition`; scarcity objective constant | `CoreEconomicsComponent` | `ScarcityCostByPeriod`, `TotalScarcityCostDefinition` | Scarcity microcase and exact matrix |
| vSPD maximization objective | `CoreEconomicsComponent` | `Economics.NetBenefit`, `Economics.Objective` | Every component and total independently recomputed |
| Gate 3 artifact projection | `CoreEnergyPreprocessor`, `CoreEnergyCase` | Immutable mappings, frozen domains, preprocessing signature | 68 exact checkpoint families; source hash unchanged; repeated-build tests |
| Continuous LP solve contract | `CoreEnergySolvePolicy`, `HighsBackend` | Optimal-only HiGHS APPSI profile with deterministic options | Representative RTD optimal solve and safe-load solver tests |
| Node/island price sign and units | `CoreEnergyPricingEngine` | Negative objective sensitivity to +1 MW required load, `NZD/MWh` | Negative/zero/scarcity prices, complementarity microcase, independent finite difference |
| Results and extension surface | `CoreEnergyResultSchema`, `CoreEnergyReportRenderer`, `ModelArtifacts` | Typed immutable results and pure renderer | Synthetic component/policy/schema/renderer replacement without assembler edits |

## Canonical projection contract

`tools.gate4.oracle_matrix` selects exactly the Gate 1 Stage 4 row and variable
families, reconstructs semantic names from Pyomo component indexes, normalizes
signed zero, and rejects any missing, extra, bound, integrality, objective, or
coefficient discrepancy at absolute tolerance `1e-9`. The retained evidence has
identical logical and structural hashes on both sides.

The island balance and bus deficit/surplus variables are Pyomo vertical-slice
scaffolding. They are intentionally excluded from the Stage 4 GAMS projection
because the corresponding vSPD bus balance and violation-variable families enter
the cumulative projection at Stage 5. Their algebra is independently validated
at Gate 4 and will be replaced/refined by the Stage 5 network components through
the public component registry.
