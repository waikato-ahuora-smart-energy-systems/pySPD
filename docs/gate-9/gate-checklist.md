# Gate 9 checklist

| Criterion | Evidence | Decision |
|---|---|---|
| Formulation-selected typed result/report classes | `DailyReportProfile`, registry, 12 typed definitions | PASS |
| Stable Python API and CLI | `PyspdApplication`, strict `ApplicationConfiguration`, `pyspd` entry point | PASS |
| Provenance on every report bundle | source/config/code/lock/solver/environment hashes | PASS |
| Serialization and round-trip | byte-identical synthetic write/read/write and hash verification | PASS |
| Structural update safety | semantic structure signature plus fail-closed rebuild policy | PASS |
| Official full-formulation execution | pinned 2025 RTD GDX; optimal SCIP/fixed-HiGHS path; 36,478 rows | PASS |
| Source-domain edge handling | inactive risk-group offer regression and official-case rerun | PASS |
| Repeat published economics | published, island, reserve, and bid file hashes exact | PASS |
| Full physical bundle determinism | alternative SCIP optimum changes detailed rows | CLASSIFIED; GATE 12 |
| Supported case types | RTD and PRSS only; other schedule types remain explicit exclusions | PASS FOR DECLARED PROFILE |
| Complete T4 historical corpus | not acquired/executed in full | GATE 12 |
| CPLEX strict compatibility | deferred by project direction | GATE 12 |
| Complete-day performance budget | no controlled matched full-day pair | GATE 12 |
| Period-to-period solver warm start | Exact 15,224-value parity; SCIP discrete start 0.47% slower; HiGHS primal start rejected after slower/raw-dual-changing smoke trial | PASS PARITY; DO NOT ENABLE |
| Locked clean environment | both base and oracle `uv sync --frozen` commands exit 0 | PASS |
| Repository quality | 239 passed, 1 skipped; Ruff and mypy pass | PASS |
| Independent human sign-off | not required by project direction | NOT APPLICABLE |

Decision: **Gate 9 is closed for the named engineering-candidate profile.**
The carried-forward items are claim limitations, not completed parity evidence.
