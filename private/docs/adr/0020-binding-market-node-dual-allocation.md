# ADR-0020: Certify binding market-node dual allocation by named family

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 report profile |
| Date | 2026-09-02 |
| Decider | Project owner direction to continue evidence-based Gate 12 parity |
| Amends | ADR-0017 portable report equivalence |

## Context

At 16:25 on 2023-01-18, three `FK_SFD2201 SFD22` upper limits are binding at
85 MW. The source GDX defines `CTRLMAX` as energy at or below 85 MW and
`MW+60` as energy plus SIR reserve at or below 85 MW. SIR reserve is zero at
the optimum, so the two rows are simultaneously binding.

GAMS/HiGHS reports the `152.41571 NZD/MWh` shadow price on `CTRLMAX`; PySPD's
HiGHS solve reports `152.41571066210324 NZD/MWh` on `MW+60`. All primal,
objective, node-price, reserve-price, and published-output surfaces pass. The
same non-negative dual total is assigned to a different active row because the
LP basis is degenerate.

## Decision

Version the mapped report comparator as
`authority-pyspd-mapped-report-row-parity-zero-flow-certified-v5`. It may
certify individual market-node price differences only within one named
`CTRLMAX`, `MW+6`, and `MW+60` family when:

- reference and candidate identities are identical;
- at least two family rows exist;
- every admitted row is an upper constraint and is binding in both reports;
- every reference and candidate dual is non-negative; and
- the family dual sums agree within the cumulative Authority display-rounding
  budget.

The semantic report-certified profile advances to
`gams-pyspd-semantic-tolerance-zero-flow-report-certified-v4`. Version-3 and
version-4 mapped-row artifacts remain readable and immutable.

## Consequences

- Solver-dependent placement is visible in the raw reports and explicitly
  counted as certified; identities are never merged or renamed.
- A changed aggregate price, nonbinding row, negative dual, missing identity,
  unrelated name, or primal discrepancy fails closed.
- No general tolerance is added to market-node constraint prices.

## Rejected alternatives

- Relabeling the PySPD dual to match GAMS was rejected because it would conceal
  the HiGHS basis result.
- Accepting arbitrary equal table-wide totals was rejected as too broad.
- Requiring individual-row equality was rejected because a degenerate LP has
  no unique dual allocation across these simultaneous limits.

## Verification

Probity tests show that the exact SFD22-style reallocation passes, while a
changed aggregate and a nonbinding family member fail. The complete 2023-01-18
comparison checks 68,516 mapped values and passes with 401 classified
differences, zero above-precision values, zero missing or extra identities,
and zero unimplemented tables.

## Revisit triggers

Revisit if vSPD changes the named constraint family, if a material downstream
price or quantity fails while this rule applies, or if strict CPLEX produces a
unique common row allocation.
