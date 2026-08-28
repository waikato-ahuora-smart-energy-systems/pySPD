# Gate 1 comparator specification

## Canonical linear form

The Convert reader normalizes every row to `lower <= activity <= upper`, retains
infinite sides explicitly, and normalizes objective sense to maximize/minimize.
Row and column identity, bounds, discrete type, and coefficient sparsity are
exact. Logical hashes use sorted semantic records and hexadecimal IEEE-754
finite values; GAMS special values retain distinct tags.

For column `j`, the independent raw stationarity residual is:

`r_j = |s*c_j - sum_i(A_ij*pi_i) - rc_j|`,

where `s=1` for maximize and `s=-1` for minimize, `pi_i` is the normalized row
marginal, and `rc_j` is the column marginal/reduced cost. Its frozen scale is:

`q_j = max(1, |c_j|, |rc_j|, max_i |A_ij|)`.

The scaled stationarity norm is `max_j(r_j/q_j)`. Activity, finite row-bound,
and finite column-bound violations use the infinity norm in native units.

## Frozen thresholds

| Check | Acceptance |
|---|---:|
| Activity reconstruction | `1e-7` absolute |
| Row bound violation | `1e-7` absolute |
| Column bound violation | `1e-7` absolute |
| Regular-column raw stationarity | `1e-7` absolute |
| All-column scaled stationarity | `1e-7` |
| Free zero-objective raw stationarity guard | `1e-4` absolute |
| Native independent node price | `1e-9` absolute plus `1e-12` relative |
| Published node price | `5e-6` absolute plus `1e-12` relative |
| MIP versus fixed-RMIP objective | `0.01 NZD` absolute plus `1e-9` relative |

The separate free-column guard does not relax bounded or economic columns. Its
only observed activation was PRSS 2022 voltage-angle columns
`ACNODEANGLE_VM` at buses 485–488: raw maximum `7.3359862e-5`, scaled maximum
`6.7185931e-10`, and regular-column raw maximum `6.7185931e-10`. This behavior
is covered by an analytic test that proves the same residual fails when placed
on a bounded column.

## Price mapping

The validator computes bus prices from fixed-RMIP balance marginals, applies
the sparse vSPD bus-price postprocessing state, and maps them with independent
node/bus allocation arithmetic. For price-transfer-enabled RTD/PRSS periods it
independently identifies dead nodes from allocation factors and disconnected
buses, then traverses `node2node` links within the same electrical island until
no eligible live source remains. It never reads `o_nodePrice_TP` as a
calculation input; that parameter and the CSV are comparison targets only.

Official CPLEX results are secondary comparisons with exact keys and
case-specific discrepancy reporting. They are not used to widen active
SCIP/HiGHS thresholds.
