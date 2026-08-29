# Gate 13 — Residential-PV study replication

| Field | Value |
|---|---|
| Stage | 13 — Residential-PV counterfactual study replication |
| Gate | G13 — Residential-PV study replicated |
| Status | **PLANNED — SOURCE ENTRY NOT YET PASSED** |
| Paper | O'Leary, Atkins, and Severinsen (2026), *Energy* 360, 141862 |
| DOI | `10.1016/j.energy.2026.141862` |
| Underlying model | Explicit Gate 12-qualified PySPD formulation/profile |
| Package manager | `uv` only |
| Architecture | Class-based scenario/data/overlay/runner/metric/comparator services |

Stage 13 seeks to reproduce the paper's residential-solar modifications and
reported operational and market results using PySPD. It is a research profile,
not a silent modification of the validated v5 or v16 compatibility model.

The accessible abstract establishes a counterfactual scenario study of New
Zealand residential PV at household adoption rates within 5–20%. Hourly
distributed PV is represented as reduced grid demand at relevant nodes, then
simulated through a replica of the scheduling, pricing, and dispatch engine.
The full paper is currently unavailable to the workspace, so baseline dates,
the exact scenario set, source datasets, transformations, metric definitions,
and numerical targets remain unverified and must not be inferred.

## Entry sequence

1. Obtain the complete paper and supplements lawfully.
2. Record file hashes and bibliographic identity in
   [`paper-source-register.json`](paper-source-register.json).
3. Complete [`paper-method-register.md`](paper-method-register.md) from the full
   text, including every parameter and reported target.
4. Freeze the selected Gate 12 formulation, solver profile, historical corpus,
   and zero-PV baseline.
5. Start production implementation under Probity TDD only after the source
   checklist passes.

## Intended components

- immutable scenario definitions and source catalog;
- PV profile construction, node allocation, and temporal mapping;
- an auditable demand overlay with conservation ledger;
- deterministic baseline/scenario orchestration;
- paper-mapped operational, market, hydro, and supply metrics;
- table/figure/result comparators with digitization uncertainty where needed;
- a hash-complete reproducibility and discrepancy pack.

The governing work, tests, and exit criteria are in
[`Stage 13 — Residential-PV counterfactual study replication`](../pyomo-vspd-stage-gate-plan.md#stage-13--residential-pv-counterfactual-study-replication).
