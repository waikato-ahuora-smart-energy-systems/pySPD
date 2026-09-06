# Gate 13 checklist

| ID | Exit criterion | Current evidence | Status |
|---|---|---|---|
| `G13-01` | Complete paper and supplements lawfully acquired, hashed, and registered | Publisher page and DOI identified; abstract accessible; full text not acquired | Blocked on source acquisition |
| `G13-02` | Exact engine version, historical period, case selection, solver, and baseline extracted | Abstract is insufficient | Pending source |
| `G13-03` | Exact adoption scenarios, PV/household/weather data, units, licences, and transformations frozen | Abstract establishes only a 5–20% range and hourly PV | Pending source |
| `G13-04` | Every paper method, equation, table, figure, and target mapped to class/config/test/evidence | Initial method register created with unknowns explicit | Pending source |
| `G13-05` | Class-based PV source/profile/allocation/temporal/overlay services pass Probity TDD | Architecture specified in the governing plan | Pending implementation |
| `G13-06` | Zero-PV overlay is identical to the selected Gate 12-qualified baseline | Required test specified | Pending implementation |
| `G13-07` | PV energy and demand deltas conserve across every spatial/temporal aggregation | Conservation ledger and required tests specified | Pending implementation |
| `G13-08` | Baseline and exact paper scenarios solve deterministically with validated prices/reports | Gate 12 solver/evidence contracts will be reused | Pending execution |
| `G13-09` | Every in-scope paper result reproduced within approved precision or explained | Comparison and digitization policy specified | Pending execution |
| `G13-10` | Repeat/resume equality and unchanged v5/v16 regression fingerprints | Required tests specified | Pending execution |
| `G13-11` | Reproducibility capsule binds paper, data, config, code, lock, solver, result, metric, and report hashes | Evidence builder specified | Pending implementation |
| `G13-12` | Zero unresolved material discrepancies and honest final claim | Permitted decisions: `REPLICATED`, `PARTIALLY REPLICATED`, `NOT REPRODUCIBLE` | Pending execution |

Gate 13 is not entered for production implementation until `G13-01` through
`G13-04` have sufficient source evidence. No separate human reviewer is
required, but unavailable source material cannot be treated as reproduced.
