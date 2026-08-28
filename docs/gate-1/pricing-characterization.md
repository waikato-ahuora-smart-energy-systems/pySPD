# Gate 1 pricing characterization

| Field | Value |
|---|---|
| Status | Executed candidate; normative CPLEX comparison pending |
| Date | 29 August 2026 |
| Source | Pinned vSPD v5.0.6 |
| Primary solver | GAMS/SCIP 54.3.1 profile |
| Pricing solver | GAMS/HiGHS 54.3.1 RMIP profile |

## Proven behavior

The committed vSPD listing shows GAMS/CPLEX solving each `vSPD_NMIR` MIP,
fixing the discrete variables, and solving a final LP before returning
marginals. vSPD then defines the bus price as the marginal of
`ACnodeNetInjectionDefinition2` and maps bus prices to nodes using
`NodeBusAllocationFactor`.

The explicit characterization profile reproduces that control pattern without
changing the pinned checkout:

1. stage a private copy of the pinned source and input;
2. solve the primary MIP with SCIP;
3. snapshot lower and upper bounds for all five binary, three SOS1, and three
   SOS2 variable families;
4. fix each binary at its rounded incumbent and every SOS variable at its
   incumbent level;
5. solve the same active model as an RMIP with HiGHS;
6. require optimal termination and an objective change no larger than
   `0.01 NZD`;
7. restore the original bounds while retaining the pricing-LP solution and
   equation marginals for vSPD reporting; and
8. parse and validate the DPS node-price report, rejecting duplicate keys and
   `NA`, `UNDF`, or infinite prices.

The overlay is fail-closed: every source replacement has an exact expected
occurrence count. A changed upstream source cannot receive a partial overlay.

## Full-size sample result

| Measure | Result |
|---|---:|
| Primary SCIP MIPs | 15 optimal |
| HiGHS pricing RMIPs | 15 optimal |
| Branch-flow cleanup MIPs | 0 |
| Maximum primary-to-pricing objective delta | `0.000100002 NZD` |
| Maximum SCIP-primary to committed-CPLEX objective delta | `0.000100002 NZD` |
| Node-price records | 135 |
| Demand scenarios | 15 |
| Pricing nodes | 9 |
| Duplicate `(datetime, scenario, node)` keys | 0 |
| Non-finite/special prices | 0 |
| Observed price range | `0.030` to `326.036 NZD/MWh` |

Two clean staged runs produced identical logical solve-record hashes, identical
logical node-price hashes, and byte-identical node-price CSVs. Raw listing
hashes differed because GAMS listings embed run timestamps; logical hashes are
therefore the deterministic acceptance surface for listing content.

The earlier SCIP-only run triggered branch-flow cleanup for the 4% and 5%
demand-decrease scenarios because its MIP solution contained a small
original-space violation. The explicit fixed LP produced no cleanup solve,
which matches the committed CPLEX listing. This is control-path evidence, not
yet proof that HiGHS and CPLEX return identical node-price duals.

## Normative comparison still required

The repository does not commit the DPS CSV or `DRSOutput_TP.gdx`, so the
committed listing alone cannot supply the 135 CPLEX node prices. A full-size
native GAMS/CPLEX entitlement or Authority-produced hashed output is required.

There is also an effective-option discrepancy that must be resolved: the
committed CPLEX listing records `epopt=1e-9`, `epint=0`, `eprhs=1e-6`,
`epgap=0`, and `epagap=1e-9`, while the tagged `cplex.opt` currently contains
different `epopt`, `epint`, and `epagap` values. Gate 1 must bind the normative
oracle to the effective listing options or explain and approve the difference.

## Remaining price tests

- Compare raw CPLEX and HiGHS bus marginals before node allocation.
- Compare all 135 node prices at native precision and exact three-decimal
  report precision.
- Verify the marginal sign and units with central demand perturbations.
- Calculate primal feasibility, stationarity, reduced costs, and
  complementarity independently.
- Characterize basis and degeneracy sensitivity with repeated and perturbed
  solves.
- Add dead/disconnected node, scarcity, SOS-invalid-price, price-transfer, and
  branch-flow fallback fixtures.

The official GAMS CPLEX documentation describes `solveFinal=1` as solving the
problem with discrete variables fixed and returning duals. This profile is an
explicit, independently solved approximation of that convention and remains
non-normative until compared with the qualified CPLEX oracle.
