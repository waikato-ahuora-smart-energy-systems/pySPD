# Choosing a case study

Start from the question, then choose the narrowest workflow that answers it.

| Question | Study pattern | Main outputs |
|---|---|---|
| Can PySPD reproduce an existing case? | Baseline replay | summary, offer, node, published price |
| What happens if demand changes? | Audited demand override | dispatch, prices, losses, reserve |
| What is the value/impact of one offer? | Offer price or quantity sweep | generation, system cost, node prices |
| What happens during a generator withdrawal? | Energy and reserve availability override | violations, risk, reserve prices |
| What is the effect of a circuit derating? | Branch capacity/constraint override | branch flow, rentals, node-price separation |
| How sensitive are reserves? | Reserve-offer sweep | reserve clearing, risk setters, FIR/SIR prices |
| Does a solver backend matter? | Fixed-RMIP profile comparison | primal parity, analytical intervals, timing |
| How robust is a finding over time? | Hash-bound multi-day batch | distribution of metrics and discrepancy register |
| Can an older archive be replayed? | Legacy v3 adapter | normalized v5-compatible reports |
| Does SPD v16 change results? | Explicit formulation comparison | version-specific objective, reserve and reports |

## Study design checklist

Before running:

1. state the hypothesis and primary metrics;
2. freeze the source GDX hash and baseline configuration;
3. identify every case contributing to the requested publication;
4. define one change per scenario where practical;
5. predeclare tolerance and analytical-interval treatment;
6. choose worker count from memory capacity, not core count alone; and
7. use a distinct output directory for every run.

After running:

1. require complete case identities and successful statuses;
2. check violation quantities before economic interpretation;
3. compare objective and primal physics before prices;
4. compare like-for-like price surfaces;
5. retain both endpoints when an analytical interval explains a difference;
6. record unresolved differences rather than selecting a favorable rerun; and
7. bind the configuration, scenario record, logs, and report manifest by hash.

The following pages provide concrete recipes. Replace placeholder IDs only
after checking that the selected input contains them.

For studies that require time coupling, see the separate
[battery research profile](battery-storage.md) and its integration limitations.

```{toctree}
:maxdepth: 1

baseline-and-subsets
demand-and-offers
outages-and-constraints
reserve-and-scarcity
solver-and-batch
historical-and-versioned
historical-stress-event-atlas
battery-storage
```
