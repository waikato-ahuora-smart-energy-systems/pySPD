# Gate 10 release handbook

## Supported engineering profile

PySPD 0.1.0 exposes the class-based `vspd-v5.0.6-reserve` formulation on
Python 3.13. The qualified local profile is macOS arm64, GAMS 54.3.1 with SCIP
for the primary MIP, then all discrete variables fixed and HiGHS used for the
RMIP price solve. CPLEX, Linux x86_64 execution, strict end-to-end parity, and
the complete T4/full-day population are not qualified here.

## User operation

1. Run `uv sync --frozen --group oracle` when GDX/GAMS access is needed.
2. Confirm the formulation with `uv run pyspd formulations --json`.
3. Create a strict JSON run configuration containing the formulation ID, input
   path and SHA-256, case selection, solver profile, output path, code version,
   lock SHA-256, and environment fingerprint.
4. Run `uv run pyspd run --config CONFIG.json`.
5. Retain `manifest.json` and every CSV together; readers reject hash or row
   count changes.

Unknown configuration fields, unknown formulations, changed input hashes,
missing inputs, unsupported case types, and non-optimal solves fail closed.

## Developer and extension contract

Use immutable data contracts, a named `Formulation` subclass, composable
`ModelComponent` classes, and formulation-specific result schema/report
renderer classes. Do not add effective-date branches inside the v5 model.
Structural changes require a rebuild; value-only updates invalidate all stale
primal, dual, basis, fixed-discrete, and solution-loader state. Every behavior
change requires red-before-production Probity evidence.

## Data, solver, and validation boundaries

Inputs remain external and hash-bound; restricted GDX, oracle outputs, GAMS,
and solver binaries are not included in the wheel. Report provenance records
the input, configuration, code, lock, solver, formulation, and environment.
The Gate 9 official RTD qualification establishes a full-formulation
engineering execution, while Gate 12 owns strict prices/reports, complete-day
and all-546 replay evidence.

## Security and supply chain

Dependencies are resolved only from committed `uv.lock`; CI uses
`uv sync --frozen`. The CycloneDX 1.5 SBOM inventories all dependency groups.
The wheel and sdist are hashed in `release-manifest.json`, and an isolated uv
installation must expose the expected formulation before promotion. Never put
GAMS, GAMSPy, CPLEX, Gurobi, dataset credentials, or licence keys in source,
logs, configurations, manifests, or reports. Rotate any credential disclosed
outside its intended secret store.

Security reports should identify the affected version, input classification,
minimum reproduction, impact, and whether confidential data is involved. Until
an external support channel is assigned, keep reports private to the repository
owner; do not open a public issue containing restricted data or credentials.

## Incident severity and response

| Severity | Example | Immediate action |
|---|---|---|
| S1 critical | Wrong published price, silent infeasibility, credential exposure | Stop use/distribution, quarantine results, rotate secrets, preserve evidence |
| S2 high | Material dispatch/reserve mismatch or non-deterministic publication | Quarantine affected profile and open a blocking investigation |
| S3 moderate | Unsupported input accepted or provenance/report defect | Disable affected path and schedule a tested correction |
| S4 low | Documentation or diagnostic defect | Record and correct in the normal TDD cycle |

The repository owner is the interim incident and release owner until a named
organizational owner is recorded. This is an operational limitation, not a
public support commitment.

## Canary, quarantine, rollback, and historical rerun

A canary baseline is immutable and separately hash-bound. Candidate reports
with another formulation are `unsupported`; any missing, unexpected, or changed
file or logical-manifest hash is `quarantined`. Quarantine events are written
once under a deterministic event hash and can never update the baseline.

On S1/S2:

1. stop candidate promotion and preserve the candidate, baseline, config, lock,
   environment, solver logs, and quarantine event;
2. restore the last accepted commit and its frozen lock in a clean worktree;
3. fetch the historical input by recorded hash and rerun with the recorded
   formulation/solver profile;
4. compare manifests and independent validators before reopening use; and
5. add a red regression before any correction.

Baseline replacement is a separate reviewed operation. A passing candidate is
never sufficient authority to rewrite a baseline.

## Notices and distribution status

PySPD incorporates no GAMS or commercial-solver binary. It depends on Pyomo,
PyArrow, and optional locked groups including HiGHS and GAMSPy. Governing vSPD,
data, formulation-document, derived-evidence, dependency, and project-licence
decisions are recorded as `LIC-001` through `LIC-014` in the Gate 0 licence
register. All remain pending. The generated release manifest therefore states
`distribution_status: held`; it is an engineering artifact, not authorization
to publish a package or redistribute source data.
