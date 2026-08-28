# Gate 1 comparator specification

## Canonical linear form

The Convert reader normalizes every row to `lower <= activity <= upper`, retains
infinite sides explicitly, and normalizes objective sense to maximize/minimize.
Row and column identity, bounds, discrete type, and coefficient sparsity are
exact. Logical hashes use sorted semantic records and hexadecimal IEEE-754
finite values; GAMS special values retain distinct tags.

Convert scalar identifiers are not comparison identities. `DictMap` records are
decoded as `Family["index-1",...]`; the dictionary must cover every nonobjective
matrix row and column uniquely. Missing, duplicate-scalar, or duplicate-semantic
names fail validation. Both the original scalar hash and renamed semantic hash
are retained.

For column `j`, the independent raw stationarity residual is:

`r_j = |s*c_j - sum_i(A_ij*pi_i) - rc_j|`,

where `s=1` for maximize and `s=-1` for minimize, `pi_i` is the normalized row
marginal, and `rc_j` is the column marginal/reduced cost. Its frozen scale is:

`q_j = max(1, |c_j|, |rc_j|, max_i |A_ij|)`.

The scaled stationarity norm is `max_j(r_j/q_j)`. Activity, finite row-bound,
and finite column-bound violations use the infinity norm in native units.

## Bound duals and complementarity

The canonical marginal convention is the GAMS maximize convention retained by
Convert. For a row marginal `pi`, and column reduced cost `rc`, the nonnegative
finite-side multipliers are:

- row lower `lambda_L=max(-pi,0)` and row upper
  `lambda_U=max(pi,0)`;
- column lower `mu_L=max(-rc,0)` and column upper
  `mu_U=max(rc,0)`.

Thus `pi=lambda_U-lambda_L` and `rc=mu_U-mu_L`. A lower-only object rejects a
positive reported marginal; an upper-only object rejects a negative marginal;
a free object requires a zero marginal. Equality-row marginals and fixed-column
reduced costs are unrestricted and are not artificially split.

For row activity `a_i`, the raw products are
`lambda_L*(a_i-lower_i)` and `lambda_U*(upper_i-a_i)`. Column products are the
analogous `mu_L*(x_j-lower_j)` and `mu_U*(upper_j-x_j)`. The raw diagnostic is
the infinity norm of all finite, nonsynthetic products. The gate metric divides
each product by `p*d`, where:

- row `p=max(1,|a|,sum_j|A_ij*x_j|,|finite lower|,|finite upper|)`;
- column `p=max(1,|x|,|finite lower|,|finite upper|)`; and
- `d=max(1,|pi|)` for rows or `max(1,|rc|)` for columns.

The scaled complementarity infinity norm must not exceed `1e-6`. Dual-side
sign violation is checked in native marginal units at `1e-7`. Analytic tests
cover equality, fixed, free, one-sided, ranged, correct-side binding,
wrong-side binding, and missing-bound-side dual cases.

## Incremental Stage 4–7 projections

[`incremental-matrix-mappings.json`](incremental-matrix-mappings.json) is the
versioned projection contract. Each semantic equation and variable family is
owned by its first implementation stage and projections are cumulative. The
default mapping is exact identity after DictMap renaming. A row sign change,
ranged-row split, one-to-many component map, or eliminable auxiliary is allowed
only when an explicit entry is added to that manifest.

For an approved sign `sigma` in `{+1,-1}`, the transform is
`A'=sigma*A`, with the two transformed bounds sorted into canonical order,
`level'=sigma*level`, and `pi'=sigma*pi`. For an approved ranged split,
the lower and upper slacks remain separate and the canonical marginal is
recombined as `pi=lambda_U-lambda_L`; equality rows are never split. An approved
auxiliary must name its defining equality and exact substitution. The comparator
eliminates it algebraically before hashing and validates the defining equality
independently. The current version intentionally approves no nonidentity
transforms: later Pyomo stages must either preserve the canonical form or amend
the manifest with analytic equivalence tests before implementation.

## Frozen thresholds

| Check | Acceptance |
|---|---:|
| Activity reconstruction | `1e-7` absolute |
| Row bound violation | `1e-7` absolute |
| Column bound violation | `1e-7` absolute |
| Regular-column raw stationarity | `1e-7` absolute |
| All-column scaled stationarity | `1e-7` |
| Free zero-objective raw stationarity guard | `1e-4` absolute |
| Dual-side sign violation | `1e-7` absolute |
| Scaled complementarity infinity norm | `1e-6` |
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
