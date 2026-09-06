# Multi-period vectorisation investigation

## Outcome

Simultaneously solving independent trading periods in one Pyomo model is now
algebraically correct, but it is not a performance improvement for the current
SCIP MIP -> fixed HiGHS RMIP pathway. In two order-controlled trials, the
combined TP1+TP2 model was **35.8% to 84.5% slower**, with a mean slowdown of
**60.0%**. The production recommendation is to retain dynamically scheduled,
independent case solves.

The machine-readable result is
[`vectorized-two-period-investigation-20230922.json`](vectorized-two-period-investigation-20230922.json).

## Correctness defect found and fixed

The first combined solve exposed 16 unintended cross-period equations:

- eight AC bus-energy balances;
- four HVDC reserve-risk definitions; and
- four reserve-sharing sent-flow definitions.

The builders matched an HVDC link to an island or bus using the terminal bus
name, but omitted the `(case, date-time)` equality. Repeated bus names therefore
pulled TP1 HVDC variables into TP2 equations and vice versa. The invalid model
still reported optimal because SCIP had optimally solved the algebra it was
given; its objective was `2506.804070115` NZD below the sum of independent
optima.

The network, HVDC, reserve-data, and independent-validator indexes now require
the full period prefix. The red-first real-GDX regression permits only
`Economics.TotalViolationCostDefinition` to span periods; that row intentionally
defines one scalar total and creates no physical coupling.

After repair, all 5,610 compared generation, purchase, reserve, island-reserve,
and directed-branch-flow values pass at `1e-6`. The maximum variable difference
is `1.58e-10`, and the aggregate objective differs by `1.19e-7` NZD on a
`694.7 million` NZD objective.

## Performance evidence

| Execution order | Separate | Vectorized | Vectorized change |
|---|---:|---:|---:|
| Vectorized first | 20.656 s | 28.057 s | +35.8% |
| Separate first | 20.314 s | 37.485 s | +84.5% |
| Mean | 20.485 s | 32.771 s | +60.0% |

Reversing execution order rules out a simple import or solver warm-up benefit.
The combined model has 114,519 variables and 64,761 constraints; separate
models total 114,520 and 64,762. Vectorisation removes only one copy of the
scalar objective/total-penalty machinery. Every physical block remains linear
in the number of cases, while SCIP and HiGHS lose the smaller independent
problem boundaries.

At that observed density, 48 representative periods would create roughly
2.75 million variables and 1.55 million constraints. A 274-case pricing day
would create roughly 15.69 million variables and 8.87 million constraints.
These are count extrapolations, not full-day solve claims.

## Architectural implication

Independent periods should continue through the ten-worker dynamic scheduler:
it balances uneven solve times, isolates retries and checkpoints, and allows
each period's shortfall-transfer loop to stop independently. A single model
would force all periods to remain resident and makes one solver failure affect
the whole batch.

Vectorisation should be reconsidered for a different reason if Stage 13 adds
true inter-period physics such as battery state of charge or inter-temporal
ramping. At that point a joint model is mathematically necessary, not merely a
speed optimisation. A solver-native batch/block interface would also merit a
separate trial because it might retain independent matrices without creating
one monolithic Pyomo object.
