# Licence and provenance register

| Field | Value |
|---|---|
| Status | **Unapproved — Gate 0 hold** |
| Reviewer | Legal/licensing reviewer — TBD |
| Scope | Source, specifications, data, fixtures, solver software, derived artifacts, package distribution |

This register is an engineering inventory, not legal advice. A qualified
reviewer must approve each proposed treatment before Gate 0 passes or artifacts
are redistributed.

## Register

| ID | Material | Source/terms | Intended use | Proposed handling | Approval |
|---|---|---|---|---|---|
| `LIC-001` | vSPD v5.0.6 source | Public GitHub repository; EMI tools licence candidate | Read, characterize, adapt into PySPD, run oracle | Preserve attribution and source/commit provenance; do not redistribute archive until reviewed | Pending |
| `LIC-002` | EMI tools licence | Electricity Authority PDF | Determine model-source rights and obligations | Archive/hash after approval; record notices and any contact obligations | Pending |
| `LIC-003` | SPD Formulations v15/v16 | Transpower PDFs with restrictive copyright notice | Requirements mapping and validation | Link and hash; do not reproduce detailed text/equations; store only where permitted | Pending |
| `LIC-004` | Daily Pricing GDX | Electricity Authority dataset terms | Oracle and qualification input | Fetch by URL/date, hash each file, avoid bundling restricted/large data in wheel | Pending |
| `LIC-005` | Historical audit packs | Authority/independent audit materials | Assurance method and regression cases | Obtain access/redistribution approval; bind each case to exact profile | Pending |
| `LIC-006` | 2023 parity pack | Historical Git commit | Targeted SPD/vSPD comparisons | Retain commit/path/hash; redistribute only after review | Pending |
| `LIC-007` | 2025 commissioning-risk pack | Historical Git commit | Link/secondary-risk regression | Retain commit/path/hash; review embedded GDX/DOCX/output rights | Pending |
| `LIC-008` | GAMS runtime and Transfer API | Commercial GAMS licence | Normative oracle and optional conversion | Require valid licence; never bundle proprietary binaries | Pending |
| `LIC-009` | CPLEX | Commercial IBM licence through GAMS and/or Python | Normative parity solver | Require valid licence; record version/options, not proprietary executable | Pending |
| `LIC-010` | Gurobi | Commercial licence | Optional independent solver | Optional profile; no bundled binaries/licences | Pending |
| `LIC-011` | HiGHS/highspy | Package licence to confirm from locked metadata | Portable LP/reformulated profile | Record licence in SBOM/notices before dependency addition | Pending |
| `LIC-012` | Pyomo | Package licence to confirm from locked metadata | Modelling framework | Record exact version/licence in SBOM/notices | Pending |
| `LIC-013` | PySPD oracle-derived matrices/results | Derived from source/data/runtime | Validation and audit evidence | Retain privately by hash until source/data/solver rights are approved | Pending |
| `LIC-014` | Synthetic microcases | Project-created | Public tests/examples | Use fictional labels/data and project licence | Project decision pending |

## Provenance requirements

Every external artifact records:

- canonical title and publisher;
- source URL or repository/commit/path;
- access and effective dates;
- SHA-256 and size;
- licence/terms identifier and review decision;
- permitted storage, transformation, distribution, and retention;
- consumer requirements/tests; and
- supersession or withdrawal state.

Every derived artifact records all parent hashes, the generating source and
runtime versions, exact command/options, schema/comparator version, and result
hash.

## Distribution policy pending approval

Until legal review completes:

- Git contains links, manifests, schemas, synthetic fixtures, and project-owned
  documentation only.
- Large or third-party inputs are fetched by hash into ignored local storage.
- No GAMS, CPLEX, or Gurobi binary is bundled.
- No detailed Transpower formulation text or equation set is copied into PySPD
  documentation.
- No historical pack is republished merely because it appeared in an old Git
  tree.
- Public release and package licensing remain undecided.

## Questions for legal review

1. Does the EMI tools licence authorize the planned adaptation and public
   distribution of PySPD source?
2. What attribution, notice, feedback, contact, or sublicensing obligations
   apply?
3. May oracle-derived matrices, marginals, and normalized outputs be retained or
   published?
4. May selected public GDX records be redistributed as test fixtures, or must
   tests fetch original files?
5. May the 2023/2025 historical test packs and audit cases be redistributed?
6. What use of SPD formulation clause identifiers and paraphrased requirements
   is permitted?
7. Which project licence and notice files are required before release?

## Gate closure

The legal reviewer must mark every in-scope row `Approved`, `Approved with
controls`, or `Rejected`; add signed advice/evidence; and ensure rejected uses
are removed from scope. `Unknown` or `Pending` on a release-critical row blocks
Gate 0.
