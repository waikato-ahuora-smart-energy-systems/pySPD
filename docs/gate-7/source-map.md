# Gate 7 source and formulation map

## Reference sources

| Concern | vSPD 5.0.6 source | Pyomo implementation | Verification |
|---|---|---|---|
| Input normalization | Input GDX plus `vSPDsolve.gms` reserve preprocessing | `reserve/data.py` | canonical pinned GDX build and invariant tests |
| Reserve offers | `vSPDmodel.gms` sections 6.5.3 and 6.5.5 | `ReserveOfferComponent`, `IslandReserveComponent` | analytic product tests and exact matrix |
| Risk | `vSPDmodel.gms` section 6.5.1 | `ReserveRiskComponent` | independent risk recomputation and per-class tests |
| Scarcity | `vSPDmodel.gms` section 6.5.4 | `ReserveScarcityComponent` | block/total recomputation and exact matrix |
| NMIR sharing | `vSPDmodel.gms` section 6.5.2 | `ReserveSharingComponent` | bidirectional identities, adjacency, discrete audit |
| Reserve balance | `SupplyDemandReserveRequirement`, `IslandReserveCalculation` | `ReserveRequirementComponent` | binding/nonbinding coverage for all eight risk classes |
| Security | market-node reserve factors in section 6.6 | `ReserveSecurityComponent` | full matrix projection and Gate 5 regression |
| Economics | system cost, penalties, scarcity, share perturbations | `ReserveEconomicsComponent` | objective recomputation and exact constants |
| Pricing | `IslandReserveCalculation.m` plus energy-balance marginals | `ReservePricingEngine` | independent RHS/load finite differences |

## Equation traceability

Every active Gate 7 row family is included in the exact canonical projection.
The grouped mapping below covers all vSPD declarations; families with zero rows
in the pinned case are still constructed and tested analytically when enabled.

| Group | vSPD equation families | Pyomo owner |
|---|---|---|
| Offer products | `PLSRReserveProportionMaximum`, `ReserveInterruptibleOfferLimit`, `ReserveOfferDefinition`, `EnergyAndReserveMaximum` | `ReserveOfferComponent` |
| Scarcity identities | `HVDCRiskReserveShortFallCalculation`, `ManualRiskReserveShortFallCalculation`, `GenRiskReserveShortFallCalculation`, `HVDCsecRiskReserveShortFallCalculation`, `HVDCsecManualRiskReserveShortFallCalculation`, `RiskGroupReserveShortFallCalculation` | `ReserveScarcityComponent` |
| DC/manual risk | `RiskOffsetCalculation_DCCE`, `RiskOffsetCalculation_DCECE`, `HVDCRecCalculation`, `HVDCIslandRiskCalculation`, `ManualIslandRiskCalculation` | `ReserveRiskComponent` |
| Generator/group/link risk | `GenIslandRiskCalculation(_1)`, `GenIslandRiskGroupCalculation(_1)`, `AClineRiskGroupCalculation(_1)` | `ReserveRiskComponent` |
| Secondary risk | `HVDCIslandSecRiskCalculation_GEN(_1)`, `HVDCIslandSecRiskCalculation_Manual`, `HVDCIslandSecRiskCalculation_Manu_1` | `ReserveRiskComponent` |
| General sharing | `EffectiveReserveShareCalculation`, `BothClearedAndFreeReserveCanBeShared`, `SharedReserveLimitByClearedReserve` | `ReserveSharingComponent` |
| Direction/control | `ReserveShareSentLimitByHVDCControlBand`, `FwdReserveShareSentLimitByHVDCCapacity`, `ReverseReserveOnlyToEnergySendingIsland`, `ReverseReserveShareLimitByHVDCControlBand`, `ForwardReserveOnlyToEnergyReceivingIsland`, `ReverseReserveLimitInReserveZone`, `ZeroReserveInNoReserveZone` | `ReserveSharingComponent` |
| Zones/sending | `OnlyOneActiveHVDCZoneForEachReserveClass`, `ZeroSentHVDCFlowForNonSendingIsland`, `RoundPowerZoneSentHVDCUpperLimit`, `HVDCSendingIslandDefinition`, `OnlyOneSendingIslandExists`, `HVDCSendMustZeroBinaryDefinition` | `ReserveSharingComponent` |
| NMIR curves | `HVDCSentCalculation`, `HVDCFlowAccountedForForwardReserve`, `ForwardReserveReceivedAtHVDCReceivingIsland`, `HVDCFlowAccountedForReverseReserve`, `ReverseReserveReceivedAtHVDCSendingIsland`, all energy/reserve lambda, flow, and loss definitions | `ReserveSharingComponent` |
| Effective-share penalty | CE/ECE effective-share calculations and `ExcessReserveSharePenalty` | `ReserveSharingComponent` |
| Cover | `IslandReserveCalculation`, `SupplyDemandReserveRequirement` | island/requirement components |

## Variable traceability

The canonical projection exactly matches these active families and counts:

| Families | Count |
|---|---:|
| `RESERVE`, `RESERVEBLOCK` | 594 + 11,880 |
| island, generator, and group risk | 32 + 92 + 4 |
| reserve shortfall totals | 12 + 92 + 2 |
| reserve shortfall blocks | 276 + 2,116 + 58 |
| reserve deficits | 4 CE + 4 ECE |
| sharing/effective/NFR variables | 65 |
| NMIR energy/reserve lambdas and flow/loss variables | 138 |
| NMIR zone/sending binaries | 16 |
| **Total Gate 7 oracle columns** | **15,381** |

The portable SOS2 layer adds 108 interval binaries and 128 adjacency rows. It
is excluded from the oracle projection because it encodes, rather than changes,
the GAMS SOS2 semantics. Boundary and adjacency tests plus the solved full case
qualify this representation.

## Applicability decisions

- The pinned case has no active HVDC-secondary or directional AC-link risk
  rows. Both domains and equations remain implemented; secondary behavior and
  every risk-class cover state are exercised by analytic tests. Directional
  factors are data driven and included in the independent recomputation.
- vSPD 5.0.6 has no separately declared “commissioning risk” variable or
  equation family. Such records enter the existing group/directional risk
  inputs and therefore require no invented Pyomo family.
- Native CPLEX/`solvefinal` and Linux execution remain deferred under ADR-0008
  and ADR-0011. These are platform/profile limitations, not formulation gaps.
