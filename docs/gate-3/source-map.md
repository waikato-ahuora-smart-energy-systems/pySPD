# Gate 3 vSPD v5.0.6 preprocessing source map

This map freezes the procedural source boundary at the pinned vSPD v5.0.6
`Programs/vSPDsolve.gms`. Line references are descriptive anchors to that
version; the GAMS checkpoint is the executable authority.

| Source block | GAMS derivation | Python owner | Named evidence/artifacts | Focused tests |
|---|---|---|---|---|
| §3, lines 300–344 | load the selected GDX symbols | `CaseInput` | faithful sparse set/parameter access and GDX date | Gate 2 canonical tests; pipeline fixture |
| §3 compatibility, 350–367 | Gregorian date, loss tolerance, directional risk availability | `CompatibilityStep`, `CompatibilityProfile` | `compatibility`; tolerance and regime flags | before/on/after tests for 2019-03-28, 2023-04-27, and 2025-03-17 |
| §4, 369–397 | ordered input overrides | `OverrideOperation`, `apply_overrides_with_provenance` | immutable override result and per-key provenance log | scale → increment → value precedence test |
| §5, 403–422 | selected period, node/bus/island sets, allocation totals | `TopologyStep` | `topology`; node, bus, node-island, normalized bus-node allocation | hand-derived topology and invariant mutation tests |
| §5, 425–477 | active branch, endpoint maps, AC/HVDC split | `TopologyStep` | branch definitions/connectivity, `ac_branch`, `hvdc_link` | forward-only HVDC and endpoint closure tests |
| §5, 499–578 | capacity, electrical coefficients, 0/1/3/6 loss tranches and breakpoints | `LossCurveStep` | `loss_curves`; segment MW/factor, valid segments, AC widths, HVDC cumulative breakpoints | hand-derived, disabled-model, invalid-count, property and metamorphic tests |
| §5, 580–647 | branch constraints; starts, ramps, primary/secondary, energy/reserve offers | `OfferBidLoadStep`, `ConstraintRiskStep` | `offers_bids_load`, `constraints_risk_scarcity`; filtered domains, quantities, prices, caps | participant fixture and 64-family oracle comparison |
| §5, 649–678 | dispatchable bids and market-node constraints | `OfferBidLoadStep`, `ConstraintRiskStep` | bid/block/island mappings and market-node domain/sense/limit | hand-derived valid bid and constraint tests |
| §5, 680–737 | risk groups and reserve sharing compatibility | `ConstraintRiskStep` | risk groups, adjustment factors, sharing enablement, round power, transition threshold | reserve-disabled and date-regime tests |
| §5, 738–773 | real-time flags, price-responsive ramp cap, scarcity initialization | participant and constraint steps | capped ramp, scarcity flags/defaults/reserve bands | price-responsive fixture and oracle comparison |
| §7 first loop, 913–958 | RTD target, estimated/initial load, scalability and required load | `_reconstruct_rtd_load` within `OfferBidLoadStep` | target, estimated and final scaling checkpoints plus `required_load` | RTD hand calculation and schedule non-application test |
| §7 first loop, 960–984 | node/national scarcity precedence and shared NFR inputs | `ConstraintRiskStep` | scarcity enablement, prices and limits | hand example and corpus invariants |
| post-solve, 1243–1380 | mapped-node shortfall candidate chain and transfer eligibility | `ShortfallTransferResolver` | pure transfer map, adjusted required load, transferred/untransferred flags | chained target and override/shed/island rejection tests |

## Checkpoint contract

The dependency order is fixed as:

1. `compatibility`
2. `topology`
3. `loss_curves`
4. `offers_bids_load`
5. `constraints_risk_scarcity`

Every checkpoint hashes its sorted logical artifact payload. The overall
structural signature additionally binds step class, dependencies, provided
artifacts, formulation, and all preprocessing settings.

The Gate 1 `pyspd_checkpoint_02_preprocessed.gdx` is compared independently
against 64 mapped Python artifact families. GAMS sparse absence and explicit
zero are normalized; sets are exact; parameters use an absolute tolerance of
`1e-9`. The recorded run has zero missing keys, zero extra keys, zero value
mismatches, and maximum absolute error zero.

## Intentional scope classifications

| Conditional/source area | Classification | Reason |
|---|---|---|
| PVT/DPS includes | Out of Gate 0 scope | The supported formulation is SPD/AUD, not pivot or demand sensitivity mode. |
| External override GDX absent in qualification fixtures | Reachable API, inactive profile | The ordered transform and provenance contract are tested without inventing an override file. |
| Directional risk data from 2025-03-17 | Supported synthetic boundary; not present in governed historical corpus | Before/on/after behavior is tested and the optional symbol is loaded only in the valid date regime. |
| Repeated solve-loop invocation, dead-node detection from solved generation, and shortfall amount calculation | Later solve-policy orchestration | Gate 3 implements the pure mapped-node transfer rule; solved state is supplied by later model stages. |
| Report-only and result publication calculations | Outside preprocessing | They are owned by later result-schema/report stages. |
| Linux x86_64 execution | Deferred by ADR-0011 | No Linux support or parity claim is made. |
