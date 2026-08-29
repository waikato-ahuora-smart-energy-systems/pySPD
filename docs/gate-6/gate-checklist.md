# Gate 6 checklist

| Gate criterion | Evidence | Decision |
|---|---|---|
| Solver outcomes retain raw and normalized distinctions | `GamsScipBackend` tests optimal/no-incumbent, timeout with/without incumbent, infeasible, unbounded, infeasible-or-unbounded, unavailable, and bad licence | Pass |
| Rejected states never load primal or price results | Both backends fail closed; optimal without an incumbent and limit without incumbent are rejected | Pass |
| Continuous HVDC matrix matches the oracle | [Matrix parity](oracle-matrix-parity.json): identical hashes; 16 rows, 36 columns, 88 nonzeros; all nine discrepancy counters zero | Pass |
| Portable SOS2 is mathematically equivalent and bounded | [SOS/RMIP evidence](sos-rmip-evidence.json): boundary, adjacency, integrality, size, objective/solution and observed runtime evidence | Pass |
| Native SOS2 structural form is retained | Named `SOSConstraint(sos=2)` over the identical ordered curve | Pass for structure; CPLEX execution deferred |
| Circulation/nonphysical detection and re-solve are deterministic | Analytic opposing-link and nonadjacent-lambda tests; one bounded rebuild into enforced SCIP MIP; unresolved defects raise and cannot publish | Pass |
| Fixed-MIP pricing follows the approved pathway | Explicit GAMS-SCIP primary, fix every discrete decision, relax domains/deactivate SOS, assert continuous, then HiGHS RMIP | Pass |
| Pricing model contains no omitted discrete/SOS state | Complete fix-set audit: four of four synthetic discrete decisions fixed, zero pricing discrete variables, zero pricing SOS | Pass |
| Pricing transformation is fingerprinted and limited | Primary/pricing algebra hashes identical; state hashes differ only because of approved fix/domain transition | Pass |
| Fixed-MIP duals match perturbation economics | Synthetic fixed-MIP error below `1e-9`; representative nodal price error below `2.3e-5` NZD/MWh | Pass |
| Dispatch and prices use separate immutable snapshots | Result schema reads primary model; pricing engine reads only rebuilt pricing-model duals; stale-state mutation test passes | Pass |
| Diagnostics are sufficient and capabilities explicit | Reproducible LP/MPS copies with SHA-256; SCIP/HiGHS IIS unsupported and rejected explicitly | Pass |
| Degeneracy/alternative optima are classified | Exact-breakpoint alternative interval selection is accepted only after fixing the returned incumbent; dispatch, objective, and fixed-RMIP price remain invariant | Pass |
| Representative Stage 6 case passes | [Solve/price evidence](solve-price-validation.json): optimal, 17 residuals, `2.84e-14` maximum, 523 finite node prices | Pass |
| Probity covers every Gate 6 production path | `TDD-G6-HVDC`; repository audit reports 26 records and eight implementation commits | Pass |
| Qualified platform/exclusions are explicit | macOS arm64 GAMS-SCIP/HiGHS qualified; CPLEX deferred by ADR-0008; Linux deferred by ADR-0011 | Pass with stated limitations |

## Verification commands

```text
uv run pytest tests/hvdc -q
uv run python -m tools.gate6.oracle_matrix ...
uv run python -m tools.gate6.qualification ...
uv run python -m tools.probity_audit
uv run pytest -q
uv run ruff check .
uv run mypy src tools
```

All Python and package operations use `uv`. SCIP is invoked through the licensed
GAMS 54 shell interface; the pricing solve is HiGHS and is accepted only at an
optimal termination with a loaded solution.
