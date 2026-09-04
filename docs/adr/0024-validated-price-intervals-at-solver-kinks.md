# ADR-0024: Validate price intervals at solver-dependent kinks

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-05 |
| Decider | Project owner direction that CPLEX is the gold standard and values inside validated intervals are accepted |
| Amends | ADR-0006 pricing convention and ADR-0018 portable published-price tolerance |

## Context

The first current-code replay of 2023-09-24 completed all 254 cases optimally,
but exposed three independent numerical boundaries.

First, case `231012023091815562` placed HVDC flow 0.422 MW inside the
round-power zone. Constraining it to the adjacent 190 MW source boundary
improved the objective by 0.00310 NZD and reproduced CPLEX generation and case
prices at report precision.

Second, ARI1101 is a passive zero-flow bus connected to its live parent by two
parallel lossy circuits. Treating each circuit independently produced an
interval whose lower endpoint was 0.0054 NZD/MWh too high. DC phase-angle
physics sends an incremental transfer over parallel circuits in proportion to
their susceptance, so their first-segment loss factors must be aggregated by
that same weight before deriving the one-sided price interval.

Third, reserve prices differed where either a reserve-definition row was at a
one-sided marginal kink or CPLEX accepted a nearby reserve-loss breakpoint
within solver optimality tolerance. Independent HiGHS perturbations reproduced
the opposite exact marginal. Nearby-breakpoint alternatives were at most
0.066 NZD worse on objectives near 580,000 NZD.

The next-day replay exposed the same LP-basis distinction on radial AC branch
`KIN_T5.L5`. Its flow was exactly the cumulative width of three piecewise-loss
segments. HiGHS selected the third-segment marginal loss and CPLEX the adjacent
fourth-segment marginal loss. The corresponding radial-leaf price endpoints
are analytical subgradients of the same source loss curve.

## Decision

- Canonicalize a solved round-power RZ state to its source zone-exit boundary
  only when it is no more than 1 MW away and a second fixed-RMIP solve loses no
  more than 0.01 NZD.
- For a passive component with parallel live boundaries to the same parent,
  derive each directional loss factor as the absolute-susceptance-weighted
  aggregate of those circuits. Intersect intervals only across distinct live
  parents.
- Expose a reserve-price interval when an independently solved `1e-4` MW
  one-sided perturbation proves a distinct marginal.
- A nearby reserve-loss breakpoint may contribute an alternate reserve-price
  endpoint only when its independently solved objective loss is no more than
  both `1e-6` relative and 0.1 NZD absolute. The governed scalar solution is
  retained; the interval records the solver-tolerance-equivalent price set.
- When a radial AC branch is exactly at the cumulative boundary between two
  ordered loss segments, expose the leaf-bus interval implied by both adjacent
  loss factors. Require the live flow and loss-block levels to reproduce that
  source boundary and require the solver scalar to equal one endpoint.
- Validate continuous physics on the fixed RMIP used for accepted reports.
  SCIP remains authoritative for discrete/SOS decisions; compare the SCIP and
  fixed-RMIP objectives relative to their objective scale.
- CPLEX values inside these source- and solve-validated intervals are accepted.
  Empty intervals retain ordinary scalar comparison.

## Consequences

- No CPLEX case identifier, result value, or endpoint is embedded in model
  algebra.
- Published energy and reserve prices for 2023-09-23 through 2023-09-25 have
  zero unresolved rows. Case reserve prices also have zero unresolved rows;
  all accepted differences remain visible as interval-certified differences.
- Low reserve-price kinks require extra fixed-RMIP sensitivity solves. This is
  an explicit validation cost and does not replace SCIP as the primary MIP
  solver or HiGHS as the pricing solver.
- Raw allocation differences and summary rounding remain visible and are not
  relabelled as exact scalar parity.

## Rejected alternatives

- A CPLEX-compatible selection switch was rejected because the accepted
  convention is the source-defined export endpoint plus validated intervals.
- Intersecting independent parallel-circuit intervals was rejected because it
  ignores the common phase-angle transfer split.
- Accepting all low prices by tolerance was rejected because every interval
  endpoint must come from a successful independent perturbation or bounded
  breakpoint solve.
- Selecting one solver's radial loss-segment endpoint was rejected because the
  source piecewise-linear curve admits both adjacent subgradients at the kink.
- Forcing the CPLEX reserve quantities was rejected because rounded report
  values can overconstrain the fixed RMIP and do not identify its SOS support.

## Verification

- Unit tests cover round-power candidate distance, parallel-circuit
  susceptance weighting, radial AC-loss breakpoints, one-sided reserve
  intervals, and fail-closed report containment.
- The three certified streams contain 821 optimal, independently valid cases.
  Their record hashes are
  `f8908981c2ad6a6cafb4ed884712c194665150430e23841f1b0c5eb8385d1a5b`,
  `efe96f61325781e87f3e5b6e9f88c99107467e999e33fc6b697a748e979c1e13`,
  and `f05672e032abecc2b07b169853e8930e6d44d5220b59eaa8d1def433cc91ae2b`.
- Their CPLEX comparisons record zero unresolved PublishedEnergyPrices,
  PublishedReservePrices, and ReserveResults rows.

## Revisit triggers

Revisit if a new day requires a wider MW, relative, or absolute objective
bound; if a purported interval endpoint cannot be reproduced; if parallel
circuits have incompatible phase-angle orientation; if a non-radial AC loss
kink needs certification; or if the added sensitivity solves materially impair
production throughput.
