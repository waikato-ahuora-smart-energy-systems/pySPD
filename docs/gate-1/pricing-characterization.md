# Gate 1 pricing characterization

| Field | Value |
|---|---|
| Status | Active adequate SCIP/HiGHS reference under ADR-0008 |
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
   `NA`, `UNDF`, or infinite prices;
9. on the final demand scenario only, export the fixed-LP solution plus a GAMS
   Convert `DumpGDX` matrix and `DictMap` name dictionary; and
10. canonicalize the GDX content, recompute matrix activity/bounds/stationarity,
    and derive node prices independently from balance-equation marginals and
    node-to-bus allocation factors.

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
| Canonical fixed-LP rows / columns / nonzeros | `33,131 / 58,232 / 111,925` |
| Maximum independent activity delta | `3.92e-11` |
| Maximum row / column bound violation | `1.17e-10 / 0` |
| Maximum stationarity residual | `6.25e-10` |
| Native independent node-price delta | `0` across 9 final-scenario nodes |
| Three-decimal CSV price delta | at most `0.000500001 NZD/MWh` |

Two clean staged runs produced identical logical solve-record and node-price
hashes, byte-identical node-price CSVs, and identical logical hashes for the
input, fixed-LP solution, Convert matrix, name dictionary, and normalized linear
matrix. Raw listing hashes differed because GAMS listings embed run timestamps;
logical hashes are therefore the deterministic acceptance surface.

The independent price validator does not read `busPrice`, `o_nodePrice_TP`, or
`o_drsnodeprice` to calculate its prices. It reads the marginal of each
`ACnodeNetInjectionDefinition2` balance equation, applies
`nodeBusAllocationFactor`, and only then compares the derived values with the
native GDX output and three-decimal CSV. The final-scenario native comparison
was exact for all nine pricing nodes.

The earlier SCIP-only run triggered branch-flow cleanup for the 4% and 5%
demand-decrease scenarios because its MIP solution contained a small
original-space violation. The explicit fixed LP produced no cleanup solve,
which matches the committed CPLEX listing. This is control-path evidence for
the active SCIP/HiGHS pathway, not a claim of CPLEX-identical duals.

## Deferred CPLEX comparison

The repository does not commit the DPS CSV or `DRSOutput_TP.gdx`, so the
committed listing alone cannot supply the 135 CPLEX node prices. A future
full-size native GAMS/CPLEX entitlement or Authority-produced hashed output is
needed for a CPLEX-specific parity claim, but it does not block current work.

There is also an effective-option discrepancy that must be resolved: the
committed CPLEX listing records `epopt=1e-9`, `epint=0`, `eprhs=1e-6`,
`epgap=0`, and `epagap=1e-9`, while the tagged `cplex.opt` currently contains
different `epopt`, `epint`, and `epagap` values. This discrepancy remains for
the deferred CPLEX cross-validation profile.

## Remaining price tests

- Compare raw CPLEX and HiGHS bus marginals before node allocation.
- Extend native marginal validation from the final matrix snapshot to all 15
  scenarios; all 135 CSV prices are already structurally and numerically valid.
- Verify the marginal sign and units with central demand perturbations.
- Add explicit complementarity metrics; activity, bound feasibility, and
  stationarity are independently checked for the final fixed LP.
- Characterize basis and degeneracy sensitivity with repeated and perturbed
  solves.
- Add dead/disconnected node, scarcity, SOS-invalid-price, price-transfer, and
  branch-flow fallback fixtures.

The active profile is the normative interim reference under ADR-0008 whenever
all operational SCIP/HiGHS solves report status `1/1` and every evidence check
passes. It does not establish CPLEX-identical duals; that claim remains deferred.
