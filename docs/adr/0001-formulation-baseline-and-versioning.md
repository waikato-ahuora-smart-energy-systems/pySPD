# ADR-0001: formulation baseline and versioning

| Field | Value |
|---|---|
| Status | Accepted by project direction |
| Date | 28 August 2026 |
| Deciders | Project direction; technical implementation agent |

## Context

The public vSPD baseline is v5.0.6 at commit
`21b1cf33f5607399331dcb1c03270348def5ccc8`. It implements behavior associated
with SPD Formulation v15, including Link Risk and AC Secondary Risk. SPD
Formulation v16 subsequently introduced an equal-price tie-break, paired-BESS
mode restrictions, and a reserve-price change. Mixing those rules would make
neither historical nor current results reproducible.

Historical v3/v4 inputs also have incompatible schemas and formulation profiles.
Date-based hidden branching cannot express these assurance boundaries safely.

## Decision

1. The first compatibility formulation is identified as `vspd-5.0.6` and pins
   the exact source commit, tree, configuration overlay, data profile, and
   solver profile.
2. `Vspd506Formulation` is a concrete class selected explicitly by configuration.
3. SPD Formulation v15 is mapped clause-by-clause as governing intent; pinned v5
   behavior remains the compatibility oracle.
4. `Spd16Formulation` is a separate future class. It replaces/adds only the
   component, preprocessing, pricing, result, and renderer classes affected by
   approved v16 deltas.
5. Input schema/effective date is validated against the chosen formulation but
   does not choose it silently.
6. v3.0.4, v3.1, and v4 remain separate historical profiles. Their evidence
   cannot certify v5 by substitution.
7. Every result includes formulation ID, source commit, data profile, solver
   profile, and run-manifest hash.

## Consequences

- Historical v5 results remain reproducible after v16 support is added.
- Some code exists as formulation-specific classes rather than a universal
  conditional implementation.
- Cross-version comparisons are explicit and testable.
- A new formulation requires Gate 11 and affected prior-gate reruns.

## Rejected alternatives

- **Always use latest rules:** breaks historical reproducibility.
- **Select by data date:** hides user intent and can apply the wrong rule to
  backfilled or counterfactual data.
- **Scatter `if version/date` checks:** creates untraceable mixed formulations.
- **Treat v15 Link/Secondary Risk as v16 changes:** factually incorrect and
  corrupts the delta boundary.

## Verification

- Registry tests require explicit formulation selection.
- Compatibility tests reject invalid formulation/schema/date combinations.
- A Gate 11 test proves v16 extension does not change v5 goldens.
- Every manifest and report exposes the selected formulation ID.

## Revisit triggers

- The Authority publishes a new vSPD version or authoritative v16-aligned source.
- A governing formulation/source conflict changes the intended compatibility
  claim.
- A historical input adapter is promoted into release scope.
