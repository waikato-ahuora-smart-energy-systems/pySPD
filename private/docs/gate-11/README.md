# Gate 11 — SPD v16 controlled-formulation evidence

Gate 11 is closed at the amended engineering-formulation boundary. PySPD now
contains an explicitly selected, class-composed `spd-v16.0-reserve` profile for
sources dated on or after 23 June 2026, while the historical
`vspd-v5.0.6-reserve` profile remains separately selectable and structurally
unchanged.

This gate authorizes continued engineering and Gate 12 parity work. It does
not claim strict vSPD parity, authorize public distribution, qualify CPLEX, or
qualify every PRSS/NRSS/full-day execution path.

| Artifact | Purpose |
|---|---|
| `source-register.json` | Hash-bound authoritative formulation, source, and GDX inputs |
| `delta-register.md` | Requirement-to-class/test mapping and known source differences |
| `compatibility-matrix.md` | Explicit formulation, date, data, solver, and claim boundary |
| `qualification.json` | Machine-readable RTD solve, matrix, price-validation, and regression evidence |
| `gate-checklist.md` | Criterion-by-criterion Gate 11 disposition |
| `closure-decision.md` | Exact authorization, holds, and Gate 12 transfers |
| `tdd/` | Probity red/green records and environment manifest |

The qualification uses the project-approved portable pathway: GAMS/SCIP MIP,
snapshot and fix every discrete variable including `BATTERYCHARGINGMODE`, then
GAMS/HiGHS RMIP. The corresponding Pyomo profile uses SCIP for the primary MIP
and HiGHS for the fixed-discrete pricing LP. Both pathways must report optimal;
their cross-implementation output differences remain Gate 12 evidence debt.

