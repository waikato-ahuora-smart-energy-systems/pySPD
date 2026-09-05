# Interpreting parity

## “Optimal” is necessary, not sufficient

SCIP, CBC, HiGHS, CLP, CPLEX, and GAMS can all report successful optimization
while producing different values. Common causes include:

- different but equivalent MIP/SOS supports;
- continuous alternate optima;
- different LP bases and dual allocations;
- non-differentiable piecewise-loss breakpoints;
- solver feasibility/optimality tolerances; and
- genuinely different data or algebra.

Start with source hashes and model state. Do not begin by changing tolerances to
make a final price pass.

## Comparison order

| Order | Surface | Why |
|---:|---|---|
| 1 | identities/status | Prevents comparing different populations |
| 2 | violations | Establishes whether relaxation/scarcity is active |
| 3 | objective | Detects material economic/algebra differences |
| 4 | primal physics | Separates model differences from dual selection |
| 5 | fixed discrete/SOS state | Explains fixed-RMIP basis changes |
| 6 | raw duals | Diagnoses solver/basis behavior |
| 7 | repaired/node prices | Tests market mapping conventions |
| 8 | published prices | Tests weighting and rounding last |

## Numerical tolerances

Use the precision of the reference field and a predeclared numerical tolerance.
For a CPLEX CSV stored to three decimals, a value within `0.0005` is consistent
with display rounding. Full-precision outputs deserve tighter numerical checks,
subject to the relevant solver feasibility boundary.

Report absolute and relative differences, but do not use relative error alone
near zero. Preserve signed differences when diagnosing systematic bias.

## Analytical intervals

At a verified kink, the market value can have a closed interval of valid
marginals. Accept a reference scalar when:

```text
reported_lower - tolerance ≤ reference ≤ reported_upper + tolerance
```

The interval must come from model/source structure and independent perturbation
or dual evidence. It must not be constructed from the observed reference after
the fact. Empty interval fields remain scalar comparisons.

Prices at zero-flow passive nodes may not affect the primal optimum, but they
can propagate into node or published reports. Keep them visible and classify
them; do not delete them merely because flow is zero.

## Daylight-saving and time identities

Use source case ID, source datetime, and trading period together. Spring and
autumn transitions can create 46- and 50-period days. Do not “fix” a time shift
by row position; reconcile the actual datetime/trading-period mapping.

## A valid discrepancy disposition

Each material difference should end as one of:

- corrected model/data/report defect;
- accepted reference display rounding;
- independently certified analytical interval;
- certified alternative primal allocation with invariant objective/physics;
- explicitly out-of-scope field; or
- unresolved blocker.

“Both solvers said optimal” is diagnostic context, not a disposition.
