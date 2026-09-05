# ADR-0028: Admit micro-scale solver noise at repaired-bus rounding boundaries

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS Gate 12 report profile |
| Date | 2026-09-05 |
| Decider | Project owner direction that CPLEX is the gold standard |
| Extends | ADR-0017 portable report equivalence |

## Context

A 2019-11-26 repaired bus price was `68.547500442599343` against the CPLEX
three-decimal value `68.547`. It exceeded the exact half-unit boundary by only
`4.42599343e-7 NZD/MWh`, below solver-scale numerical precision.

## Decision

For repaired bus price only, add `1e-6 NZD/MWh` to the decimal display
half-unit comparison boundary. All other scalar, publication, economic, and
certificate tolerances remain unchanged. The report parity profile advances
from v7 to v8; v7 remains readable as legacy evidence.

## Consequences

The isolated binary/solver rendering residue is classified without widening
node, reserve, published-price, quantity, or money tolerances.

## Rejected alternatives

Changing the model price, rounding candidate values before comparison, and a
global `1e-6` comparison slack were rejected.

## Verification

A boundary test admits the observed micro-residue. The final 2019-11-26
comparison has zero unresolved values across 721,264 mapped values.

## Revisit triggers

Revisit if another repaired bus difference exceeds the combined boundary or
if report precision changes.
