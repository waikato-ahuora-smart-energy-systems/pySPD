# Consecutive CPLEX clean-streak corpus

This immutable corpus contains three consecutive vSPD v5.0.6 input days and
their original CPLEX-produced result CSVs from the user-supplied archive. The
dates are 2023-09-23, 2023-09-24, and 2023-09-25, immediately following the
fully diagnosed 2023-09-22 day.

The corpus is separate from `cplex_reference`, whose ten dates were selected
by a reproducible random ranking. `manifest.json` binds every input and result
tree by byte count and SHA-256. The data test also requires every archived
summary row to report solve status 1.

The qualification stopping rule is deliberately strict: the streak advances
only when a complete SCIP MIP -> fixed-discrete -> HiGHS RMIP replay has no
unresolved CPLEX difference. Differences proven to lie on a previously
accepted analytical dual interval or equivalent-allocation face are certified
rather than hidden; any other difference breaks the streak and must be
diagnosed before proceeding.
