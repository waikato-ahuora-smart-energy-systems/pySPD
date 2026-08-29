# Gate 5 vSPD v5.0.6 AC-network source map

The executable authority is pinned `Programs/vSPDmodel.gms` and
`Programs/vSPDsolve.gms`. The Gate 1 semantic Convert dictionary supplies stable
family/index names and its matrix GDX supplies bounds and coefficients.

| vSPD source family/behavior | Python owner | Stable model/artifact names | Validation |
|---|---|---|---|
| `bus`, `NodeBus`, `BusIsland`, reference-node mapping | `NetworkData`, `NetworkDomainsComponent` | `NetworkDomains.Bus`; immutable node/bus/island mappings | Exact matrix; two/three-bus, disconnected and dead-node tests |
| `ACnodeNetInjectionDefinition1` | `ACNetworkComponent` | `ACNetwork.ACNodeNetInjection`, `ACNodeNetInjectionDefinition1`; `network_flow_balance` | Exact 923-row projection; independent flow-balance residuals |
| `ACnodeNetInjectionDefinition2` | `ACNetworkComponent` | `ACNodeNetInjectionDefinition2`, bus deficit/surplus; `energy_balance` | Exact allocation/load/loss coefficients and row bounds; independent resource balance |
| `ACBranchMaximumFlow` and reverse ratings | `ACNetworkComponent` | `ACBranchMaximumFlow`, `SurplusBranchFlow` | Forward/reverse capacity and congestion-price tests; exact 2,088 rows |
| `ACBranchFlowDefinition` | `ACNetworkComponent` | `ACBranchFlow`, `ACBranchFlowDirected` | Forward and backward analytic tests; exact 1,044 rows |
| `LinearLoadFlow`; reference angles | `ACNetworkComponent`, `NetworkSolvePolicy` | `ACNodeAngle`, `LinearLoadFlow`; reference angles fixed at zero | Two/three-bus hand results; exact bounds and coefficients |
| `ACBranchBlockLimit`, `ACDirectedBranchFlowDefinition` | `ACNetworkComponent` | directional segment flows and composition rows | Boundary and direction tests; exact 11,886 rows |
| `ACBranchLossCalculation`, `ACDirectedBranchLossDefinition` | `ACNetworkComponent` | directional segment losses and totals | Fixed/PWL analytic tests; independent loss residuals; exact 11,886 rows |
| `BranchSecurityConstraintLE/GE/EQ` | `NetworkSecurityComponent` | named LE/GE/EQ rows and deficit/surplus slacks | Every sense: binding/nonbinding where mathematically applicable and both EQ slack directions; exact factors |
| `MNodeSecurityConstraintLE/GE/EQ` | `NetworkSecurityComponent` | named LE/GE/EQ rows and deficit/surplus slacks | Offer and signed bid factors; every sense and slack direction; exact factors |
| Network violation terms in `SystemPenaltyCostDefinition` | `NetworkEconomicsComponent` | bus, branch-flow, branch-security, market-node, ramp and movement penalties | Exact GAMS coefficients via cumulative matrix; slack-choice analytic tests |
| Bus/node marginal transformation | `NetworkPricingEngine` | raw bus duals, bus prices, allocation-weighted node prices, dead-node set | Congestion separation; full-rebuild finite difference |
| Branch loss/rental reporting formulas | `IndependentNetworkValidator`, `branch_rentals` | immutable validation report and rental mapping | Positive congestion rental and representative-case recomputation |
| Gate 3/raw data projection | `NetworkPreprocessor`, `NetworkCase` | immutable nested `NetworkData`; Gate 3 structural signature retained | Representative 923-bus case and exact semantic matrix |

## Canonical projection contract

`tools.gate5.oracle_matrix` selects every Stage 5 AC/loss/security row family and
all variables needed to validate its energy, scarcity, flow, loss, angle, and
slack coefficients. It restores fixed reference-angle columns, omits genuinely
unused angle columns exactly as Convert does, normalizes signed zero, and
serializes finite numbers at `1e-12` precision. It rejects any identity, bound,
integrality, objective, nonzero, or coefficient difference beyond `1e-9`.

The retained projection has identical semantic structure and logical content on
both sides. The independent validator does not evaluate Pyomo constraint bodies;
it recomputes each identity from immutable inputs and loaded variable values.
