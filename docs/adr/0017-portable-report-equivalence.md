# ADR-0017: Govern portable report equivalence separately from strict solver identity

| Field | Decision |
|---|---|
| Status | Accepted by project direction for the SCIP/HiGHS Gate 12 profile |
| Date | 2026-09-01 |
| Decider | Project owner direction that SCIP/HiGHS is an adequate current solve pathway, with CPLEX validation deferred |
| Scope | Authority/PySPD mapped report-row comparison only |

## Context

The provenance-clean 2022-11-06 replay reaches optimal SCIP primary and
fixed-discrete HiGHS pricing solves in all 196 prefix cases. Physical, objective,
island-reserve, price, publication, risk, and summary surfaces pass their
existing Gate 12 validators. Two report representations remain solver-sensitive:

- branch endpoint prices expose raw bus duals at five decimal places, although
  the portable raw-price policy is `0.001 NZD/MWh`; and
- offer-level FIR/SIR variables can select different points on the same optimal
  allocation face while island cleared reserve and every economic surface agree.

Treating either difference as an unbounded sparse-zero fill or silently copying
the GAMS row would be invalid. Requiring identical LP allocation variables would
also overstate what the currently approved portable solver pathway promises.

## Decision

Use the versioned
`authority-pyspd-mapped-report-row-parity-zero-flow-certified-v3` profile for
SCIP/HiGHS report evidence:

1. All Authority and candidate row identities remain exact and complete.
2. All ordinary quantities retain half of the Authority display unit.
3. Branch endpoint and branch marginal prices use the already approved portable
   raw-price tolerance of `0.001 NZD/MWh`; branch rentals retain the approved
   `0.01 NZD` economic tolerance.
4. Independently certified zero-flow price identities remain restricted to the
   exact hash-bound certificate.
5. Offer FIR/SIR alternatives are classified only when the identity sets are
   identical, every reference and candidate value is nonnegative, and the total
   differs by no more than the sum of the Authority rows' individual rounding
   half-units. The separately compared island cleared-reserve rows must also
   pass; the semantic bundle must prove optimal solves and the governed physical
   and economic surfaces.
6. Missing rows, extra rows, negative allocations, aggregate drift, an invalid
   certificate, or any other above-tolerance value fail closed.

The mapped-row artifact is hash-bound to the source, work item, reference and
candidate bundles, schema crosswalk, and zero-flow certificate before semantic
`report-field` acceptance.

## Consequences

- The portable profile makes a transparent equivalence claim, not a claim that
  SCIP/HiGHS reproduces every GAMS basis-dependent variable value.
- Strict CPLEX parity remains a separate Gate 12 obligation and receives no
  relaxation from this decision.
- Expanding the portable comparator to another observable requires a new
  versioned decision and probity tests.
- A future common-optimal-face/range certificate may strengthen the offer-level
  evidence without rewriting this immutable first-date result.

## Evidence

The 2022-11-06 completion certificate is
[`../gate-12/report-completeness-20221106.json`](../gate-12/report-completeness-20221106.json).
The comparator has positive and negative probity tests, including an unequal
offer-reserve aggregate that must fail.
