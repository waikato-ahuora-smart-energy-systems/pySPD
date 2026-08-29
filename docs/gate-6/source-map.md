# Gate 6 vSPD v5.0.6 HVDC and MIP-pricing source map

The executable authority is pinned `Programs/vSPDmodel.gms` and
`Programs/vSPDsolve.gms`. The Gate 1 semantic Convert matrix/dictionary supplies
the continuous HVDC row, column, bound, and coefficient oracle.

| vSPD source family/behavior | Python owner | Stable model/artifact names | Validation |
|---|---|---|---|
| HVDC link, end-bus, capacity, direction, and loss data | `HvdcData`, `HVDCDomainsComponent` | immutable links/breakpoints; `HVDCDomains` | Raw-GDX projection; forward/reverse, outage, zero/capacity tests |
| `HVDClinkMaximumFlow` | `HVDCTransmissionComponent` | `HVDCLinkMaximumFlow`; `hvdc_maximum_flow` | Exact four-row representative projection; capacity/outage tests |
| `HVDClinkLossDefinition` | `HVDCTransmissionComponent` | `HVDCLinkLosses`, `HVDCLinkLossDefinition` | Exact coefficients; fixed/PWL loss and boundary tests |
| `HVDClinkFlowDefinition` | `HVDCTransmissionComponent` | `HVDCLinkFlow`, `HVDCLinkFlowDefinition` | Exact coefficients; forward/reverse analytic solves |
| `LambdaDefinition` and loss breakpoints | `HVDCTransmissionComponent` | `Lambda`, `LambdaDefinition` | Exact weighted-lambda projection; nonadjacent detection |
| Native SOS2 loss curve | `HVDCTransmissionComponent` | `NativeSOS2` | Named structural representation and curve-data equivalence; native CPLEX execution deferred |
| Portable SOS2 reformulation | `HVDCTransmissionComponent` | `SOSIntervalBinary`, selection and adjacency rows | Boundary, adjacency, integrality, size, objective, price, and observed-performance evidence |
| Discrete demand | `DiscreteDemandComponent` | `PurchaseBlockBinary`, `DemBidDiscrete` | Acceptance test; complete fix-set audit |
| HVDC terms in bus balance and security | `HVDCACNetworkComponent`, `HVDCSecurityComponent` | rebuilt energy-balance and LE/GE/EQ security rows | Exact cumulative matrix plus independent residuals |
| Circular/nonphysical flow detection and re-solve | `detect_nonphysical_hvdc`, `HvdcSolvePolicy` | issue tuple, bounded one-transition enforcement | opposing-flow and nonadjacent-lambda tests; enforcement failure is rejected |
| SCIP primary MIP | `GamsScipBackend` | `MipSolveResult` with incumbent, bound, gap, raw status | Real licensed solve plus timeout/incumbent, unavailable, licence, infeasible, unbounded, and ambiguous-status tests |
| Fixed-discrete HiGHS RMIP pricing | `HvdcSolvePolicy`, `HvdcPricingEngine` | separate primary/pricing models and immutable snapshots | complete fix/SOS audit, algebra/state SHA-256, objective equality, independent finite difference |
| Diagnostic problem copies and IIS capability | `HvdcDiagnosticExporter` | LP/MPS files and hashes; explicit IIS capability | export test; unsupported IIS fails explicitly |
| Physical/economic result separation | `HvdcResultSchema`, `IndependentHvdcValidator` | primary dispatch/HVDC primals; pricing-only duals | stale-state mutation test and independent residual recomputation |

## Canonical and equivalent representation contract

`tools.gate6.oracle_matrix` selects all 16 continuous HVDC rows, 36 HVDC
columns, and 88 nonzeros from the representative case. Pyomo and GAMS logical
and structural SHA-256 values are identical and all discrepancy counters are
zero.

The portable SOS2 formulation is an approved mathematical extension because a
three-point curve creates two interval binaries, exactly one selected interval,
and endpoint/interior adjacency bounds. The pricing transition fixes every
accepted discrete value, changes only its domain, deactivates native SOS if
present, verifies no discrete/SOS structure remains, and rebuilds from the
immutable case. Native CPLEX runtime equivalence remains deferred by ADR-0008;
no CPLEX result is claimed.
