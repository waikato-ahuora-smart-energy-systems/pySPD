# Gate 9 — Reports, API, qualification, and release interfaces

| Field | Value |
|---|---|
| Gate | G9 — Validated engineering release candidate |
| Started | 29 August 2026 |
| Closed | 29 August 2026 |
| Decision | **CLOSED — PASS FOR AMENDED SCIP/HIGHS EVIDENCE BOUNDARY** |
| Gate 8 dependency | Closed by commit `3aa48d0` |
| Package management | `uv` only; frozen lock verified |
| Solver profile | GAMS-SCIP MIP → fix all discrete variables → HiGHS RMIP |
| CPLEX / complete T4 / strict E2E parity | Gate 12 |
| Linux x86_64 | Deferred by ADR-0011 |
| Human independent approval | Not required by project direction |

Gate 9 supplies a stable class-based Python application service and `pyspd`
CLI, explicit formulation selection, strict hash-bound configuration, twelve
typed v5 report families, deterministic CSV/manifest serialization, complete
code/dependency/solver/run provenance, and semantic structural rebuild safety.
Topology, active-domain, integrality, SOS, or ownership changes force a rebuild;
value-only changes invalidate primals, duals, bases, fixings, and loader state.

The pinned official RTD case completed through the public CLI after the run
found and the implementation fixed an inactive risk-group offer defect. Each
run produced 36,478 report rows across summary, island, bus, node, offer, bid,
reserve, risk, branch, constraint, published-price, and audit files. Published
energy/reserve outputs and report identities were repeatable. The full bundle
hash was not repeatable because SCIP selected a different valid primary optimum;
the affected physical/detail reports are explicitly classified as
alternative-optimum surfaces, not silently treated as exact.

This gate does not claim complete historical or CPLEX parity. Complete T4
replay, complete-day performance budgets, strict official-price/report parity,
and byte-deterministic full physical results remain Gate 12 obligations. Gate 9
authorizes Gate 10 packaging and operational assurance for a non-distributable
engineering candidate only; Gate 0 legal holds still control public release.

A later [period-to-period warm-start trial](warm-start-trial-20221106.md)
passed exact cold-path parity across 15,224 values, but SCIP discrete warm
starting was 0.47% slower on the order-balanced four-case sample. HiGHS primal
initialization was also slower and changed a degenerate raw dual. Both paths
remain opt-in diagnostics; the qualified application default remains cold.

The subsequent [GDX preparation optimization](gdx-preparation-trial-20221106.md)
vectorizes GAMS special-value classification and indexes UEL validation. It
reduced the measured four-case preparation phase by 72.08%, with exact
3,682,271-record canonical-feed parity. The optimized path is enabled.

The [indexed network model-build trial](model-build-trial-20221106.md) then
removed repeated all-to-all incidence scans and duplicate HVDC balance
construction. Four-case solve time fell 31.94%; the complete 57,073-column,
32,370-row normalized matrix matched the prior formulation exactly.

See the [closure decision](closure-decision.md),
[checklist](gate-checklist.md), [qualification evidence](qualification.json),
and [Probity records](tdd/).
