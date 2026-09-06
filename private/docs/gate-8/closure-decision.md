# Gate 8 closure decision

## Decision

Gate 8 is **closed — pass for the amended current evidence boundary** on
29 August 2026. Stage 9 is authorized.

The project owner explicitly accepted the current Gate 8 evidence boundary on
29 August 2026. The exact 546-interval population, representative whole-day
economics, and strict end-to-end price/report parity were moved intact to the
new mandatory Gate 12; they are deferred evidence, not completed Gate 8 claims.
No independent reviewer or approval is required under project direction.

## Passing basis

- Commits `93d4991` and `3c45b7e` implement the class-based orchestration,
  override, bounded shortfall, price-processing, publication, independent
  validation, and resume services.
- The representative full-formulation case is optimal through the approved
  GAMS-SCIP/fixed-124-discrete/HiGHS path and reproduces the Gate 7 objectives.
- Independent recomputation passes 1,209 price and publication identities with
  maximum error `1.78e-15`.
- Every override family, bounded-loop exit, prior-dispatch fallback,
  invalid/dead/disconnected price rule, duration weighting, degraded state, and
  resume safety contract has focused coverage.
- All 139 corrected daily inputs remain hash-bound. Static replay recovers 427
  immutable dead-node/positive-load affected cases and includes the exact
  optimal affected Gate 1 fixture.
- The focused 17-test suite and cumulative 230-test suite pass; Ruff, mypy, and
  the Probity audit pass.

## Accepted Gate 8 boundary

The Authority's v5.0.4 release supplies the affected count (546) and dates
(139), but no case-ID manifest. Gate 8 therefore accepts:

1. immutable hash binding for every declared date;
2. the recovered 427-case dead-node population;
3. exact optimal affected/control and state-machine fixtures;
4. representative end-to-end execution through publication;
5. independent validation of allocation, duration weighting, and rounding; and
6. explicit reporting of official-price differences under the approved
   non-CPLEX profile.

## Mandatory Gate 12 carry-forward

- Recover the remaining 119 active-node identities and produce the exact,
  unique 546-case manifest.
- Replay every affected interval through both pinned GAMS and PySPD.
- Execute representative normal, feature-rich, outage, and 46/50-period days.
- Resolve strict raw/published energy and reserve price parity, including the
  Gate 8 representative differences.
- Compare complete report surfaces and prove deterministic/resumable E2E runs.

Gate 8 closure does not permit an “E2E parity validated” claim. That maturity
label is reserved exclusively for Gate 12.
