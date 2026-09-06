# Gate 11 checklist

| Criterion | Evidence | Decision |
|---|---|---|
| Explicit formulation selection in API/configuration/output | application, compatibility policy, formulation/report registry tests | PASS |
| v5 behavior not silently changed | v5 structural fingerprint and cumulative suite | PASS |
| Authoritative source and immutable input hashes | `source-register.json` | PASS |
| Clause/delta traceability to class and test | `delta-register.md`; Probity evidence | PASS |
| Class-based modular extension | separate v16 preprocessors, components, formulation, pricing, result, renderer, executor | PASS |
| Date/schema compatibility fails closed | `compatibility-matrix.md`; focused tests | PASS |
| SCIP MIP → fix all discrete → HiGHS RMIP | Pyomo and Authority oracle qualification | PASS |
| Canonical matrix evidence and independent price validator | 33,601 × 62,533 oracle pricing matrix; 567 node prices | PASS |
| Affected regressions rerun | 257 passed, 1 skipped; ruff and mypy pass | PASS |
| Cross-version worked cases and differences | `delta-register.md` | PASS |
| Separate machine-readable decision | `qualification.json`; `closure-decision.md` | PASS |
| Strict cross-implementation parity | objective and reserve-price differences remain | DEFERRED TO GATE 12 |
| CPLEX validation | project direction | DEFERRED TO GATE 12 |
| PRSS full solve and NRSS orchestration | explicit compatibility limitations | DEFERRED TO GATE 12 |
| Linux x86_64 execution | project direction | SKIPPED |
| Public distribution | Gate 0 legal decisions remain pending | HELD |
| Independent human reviewer/approval | removed by project direction | NOT APPLICABLE |

Decision: **Gate 11 is closed at the amended engineering-formulation
boundary. Gate 12 is authorized; no parity or distribution claim is implied.**

