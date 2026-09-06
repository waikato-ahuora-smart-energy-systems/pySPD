# Validation baseline

| Field | Value |
|---|---|
| Status | Proposed for validation-lead and market-SME approval |
| Normative compatibility oracle | Pinned vSPD v5.0.6 under the ADR-0008 optimal SCIP-MIP → fixed-discrete HiGHS-RMIP profile |
| Deferred cross-validation | Native GAMS/CPLEX; required only for CPLEX-specific parity claims |
| Secondary comparator | Raw SPD and official market outputs where applicable |
| Initial release case types | RTD, PRSS, and RTDP when present |

## Assurance claims

Validation is layered. No single comparison supports the release claim.

- Input fidelity requires exact symbol, domain, order, presence, and special-value
  semantics.
- Algebra fidelity requires approved matrix mappings and coefficient/bound tests.
- Solve fidelity requires independent feasibility, objective decomposition,
  integrality, quality, and state-machine evidence.
- Price fidelity requires Gate 1 pricing characterization, sign/unit tests,
  pricing-model audits, and finite differences.
- Output fidelity requires exact PySPD-to-pinned-vSPD report behavior at the
  reference precision.
- Official SPD/market differences are classified independently and never used
  to rewrite the compatibility oracle silently.

## Corpus tiers

| Tier | Required content | Gate use |
|---|---|---|
| T0 analytic | Hand-calculated microcases for every rule, boundary, and failure | Every change |
| T1 smoke | Repository sample, canonical fixture, and 10–20 fast official cases once licensed | Pull requests |
| T2 stratified | At least 30 dates spanning feature and feature-pair coverage | Nightly and component gates |
| T3 history/defect | Applicable 2023/2025 packs, all 546 shortfall-transfer intervals/139 dates plus controls, and every discovered defect | Weekly and release |
| T4 qualification | All available daily Pricing GDX in the approved window for supported contained case types, plus separate corpora for any additional type | Gate 9/release |
| T5 adversarial/property | Invalid inputs, exact bounds, degeneracy, extremes, failure injection, 1,000 nightly/10,000 release seeds | Nightly/release |

Historical packs qualify only the exact formulation/data profile to which they
apply. A deferred v3/v4 pack remains provenance evidence until that profile is
implemented or a formally equivalent conversion is proven.

## Sampling and coverage protocol

T2 selection is feature-led, not random-day-led. The catalogue records:

- case type and publication duration;
- uncongested/congested and high/negative-price conditions;
- each AC/HVDC direction, loss form, outage, islanding, and dead/disconnected
  topology state;
- each reserve product, risk family, NMIR zone/direction, scarcity tranche, and
  soft violation;
- branch and market-node LE/GE/EQ constraints and factor families;
- circular/nonphysical flow, SOS boundary, invalid price, and fallback paths;
- shortfall transfer, ramping, schedule prior-output fallback, and overrides;
- date/schema boundaries, including 17 March 2025 risk-group branch input; and
- 46/50-period daylight-saving days.

At Gate 1 every in-scope branch, solve path, and report family must already have
an executed, reproducible oracle fixture and structural/solution snapshot.

## Initial comparator policy

| Quantity | Candidate rule pending Gate 1 calibration |
|---|---|
| IDs, domains, order, flags, statuses, sparse presence | Exact |
| Matrix structure/integrality/sparsity | Exact after approved mapping |
| Native matrix coefficients | `atol=1e-12`, `rtol=1e-10`, or documented source precision |
| Native scaled feasibility | Preferred `<=1e-7`; hard gate `<=1e-6` |
| Independent balance/security residual | `<=1e-6 MW` unless stricter identity applies |
| 3-decimal quantity source | `atol=5e-4 MW`, `rtol=1e-8` |
| Native loss | `atol=5e-6 MW`, `rtol=1e-8` |
| Objective/cost/rental oracle comparison | `atol=0.01 NZD`, `rtol=1e-9` |
| Raw nondegenerate price | `atol=0.001 NZD/MWh`, `rtol=1e-8` |
| PySPD versus vSPD published output | Exact at reference formatting/precision |
| Integrality | `<=1e-7` |
| Scaled LP stationarity/complementarity | `<=1e-6` after frozen normalization |

These are not approved tolerances. Gate 1 freezes the comparator equations,
scales, norms, signs, source precision, and empirical distributions before it
calibrates thresholds.

## Degeneracy policy

A total-objective match does not justify a differing primal or price. A
degeneracy classification requires:

1. certified overlapping optimum intervals and one common target `z*`;
2. objective equality at `z*`, not a loose acceptance band;
3. min/max ranges for each disputed primal over both optimal sets;
4. common feasible ranges and equal material aggregates;
5. KKT and diagnostic lexicographic/perturbation evidence for disputed duals;
6. correct published outputs under the approved pricing convention; and
7. independent validation approval.

An epsilon-optimal range is diagnostic and cannot alone certify a common
optimal face.

## Discrepancy classes

| Class | Gate effect |
|---|---|
| PySPD defect | Block |
| Oracle execution/extraction defect | Block |
| Source-data defect | Approved exclusion only with provenance and impact |
| Documented alternative optimum/dual degeneracy | Independent classification required |
| Approved formulation-version difference | Version-specific register required |
| Approved out-of-scope behavior | Must appear in release scope |
| Unresolved | Block |

Every discrepancy records the case/input hashes, fields, cause, materiality,
source, owner, expected range, expiry, regression test, reviewers, and closure
evidence. Waivers are field- and case-specific.

## Approval required

This baseline requires signatures from the market SME and independent
validation lead before Gate 0. Gate 1 may revise it only through a recorded
decision with empirical oracle evidence.
