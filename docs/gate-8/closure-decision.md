# Gate 8 decision

## Decision

Gate 8 is **held** on 29 August 2026. Stage 8 implementation is complete and
validated at component and representative-case level, but the existing gate
definition requires an exact 546-interval manifest, replay of every identity,
and representative full-day parity. Those claims cannot currently be made.

No independent reviewer is required under project direction. This hold is an
evidence boundary, not an approval wait.

## Completed basis

- Commits `93d4991` and `3c45b7e` implement the class-based orchestration,
  override, bounded shortfall, price-processing, publication, independent
  validation, and resume services.
- The representative full-formulation case is optimal through the approved
  GAMS-SCIP/fixed-discrete/HiGHS path and reproduces the Gate 7 objectives.
- Independent recomputation passes 1,209 price and publication identities with
  maximum error `1.78e-15`.
- The focused 17-test suite and cumulative 230-test suite pass; Ruff, mypy, and
  the Probity audit pass.

## Unresolved evidence

1. The Authority's v5.0.4 release supplies the count (546) and dates (139), but
   neither its body nor its assets supply case IDs.
2. Static replay recovers 427 cases whose positive initial load is mapped only
   to electrical-island zero. It exactly includes the known optimal affected
   fixture, but leaves 119 active-node modelling-inconsistency cases.
3. The remaining identities require either the Authority's source manifest or
   an exhaustive exact replay of roughly 38,000 daily cases. The previously
   tested relaxed screen is prohibited because it produced false negatives.
4. A representative whole-day PySPD/GAMS economic replay remains outstanding.

## Required decision/input

Provide the Authority's 546 case-ID manifest, authorize/provision a long-running
parallel exact enumeration and whole-day replay, or explicitly amend Gate 8 to
accept the current date-level binding plus the 427-case static population and
representative exact affected/control cases. Without one of those changes,
proceeding to Gate 9 would violate the controlled plan.
