# Stage 13 paper-method register

## Paper identity

- O'Leary, Jack; Atkins, Martin; Severinsen, Isaac (2026).
- “Operational and market impacts of residential solar photovoltaics using a
  system operator-derived dispatch framework.”
- *Energy*, volume 360, article 141862.
- DOI: [`10.1016/j.energy.2026.141862`](https://doi.org/10.1016/j.energy.2026.141862).
- PII: `S0360544226019699`.

## Abstract-verified boundary

| Topic | Abstract-level statement | Implementation consequence | Confidence |
|---|---|---|---|
| Market | New Zealand electricity market in a hydro-dominated system | Use a separately named NZ PySPD study profile | Verified from accessible abstract |
| Experiment | Historical market conditions compared with counterfactual residential-PV scenarios | Preserve one immutable baseline and explicit scenario deltas | Verified from accessible abstract |
| Adoption | Household adoption rates within 5–20% | Do not infer the exact scenario sequence until full text is acquired | Verified range only |
| PV time resolution | Hourly | Require a paper-exact temporal mapping to dispatch cases/trading periods | Verified from accessible abstract |
| Grid representation | Distributed PV is modelled as reduced demand at relevant nodes | Implement an auditable node-load overlay unless full text specifies additional algebra | Verified at high level |
| Engine | Replica of the system operator scheduling, pricing, and dispatch engine | Bind the exact paper engine version to the selected PySPD formulation | Version unknown |
| Outcomes | Wholesale prices, market stability, and energy supply | Implement only full-text-defined metrics and aggregation rules | Metric definitions unknown |

## Full-text extraction register

| Required item | Source locator | Extracted value | Status |
|---|---|---|---|
| Study dates and historical input release | TBD | TBD | Blocked |
| Market-engine/formulation version | TBD | TBD | Blocked |
| Schedule modes and case selection | TBD | TBD | Blocked |
| Solver and numerical settings | TBD | TBD | Blocked |
| Exact adoption scenario set | TBD | TBD | Blocked |
| Household counts and spatial source | TBD | TBD | Blocked |
| Capacity per participating household | TBD | TBD | Blocked |
| PV/weather source and profile construction | TBD | TBD | Blocked |
| Derating/orientation/efficiency assumptions | TBD | TBD | Blocked |
| Household/region-to-node allocation | TBD | TBD | Blocked |
| Hourly-to-dispatch temporal mapping | TBD | TBD | Blocked |
| Timezone and daylight-saving treatment | TBD | TBD | Blocked |
| Demand floor, export, and curtailment rule | TBD | TBD | Blocked |
| Hydro and other generation metrics | TBD | TBD | Blocked |
| Price and stability metrics | TBD | TBD | Blocked |
| Security, reserve, scarcity, and supply metrics | TBD | TBD | Blocked |
| Statistical/uncertainty methods | TBD | TBD | Blocked |
| Table and figure targets | TBD | TBD | Blocked |
| Reported precision and tolerances | TBD | TBD | Blocked |
| Limitations and excluded effects | TBD | TBD | Blocked |

No `TBD` value may be silently replaced by an assumption in the primary
replication profile. Assumptions belong to separately named sensitivity runs.
