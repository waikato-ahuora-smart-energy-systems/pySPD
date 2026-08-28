# Gate 1 — executable oracle and corpus

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Started | 29 August 2026 |
| Current decision | **HOLD — NOT CLOSED; SCIP/HiGHS ACTIVE REFERENCE** |
| Compatibility source | vSPD v5.0.6, commit `21b1cf33f5607399331dcb1c03270348def5ccc8` |
| Initial executed case | `RTD_202502261155_251012025022255930_20250226115400` |

Gate 1 characterization has started under the Gate 0 research authorization.
ADR-0008 treats the optimal SCIP-MIP plus fixed-discrete HiGHS-RMIP pathway as
adequate for current development. This is not permission to claim CPLEX parity;
corpus breadth, preprocessing checkpoints, finite-difference coverage, and
independent review remain open.

## Current evidence

| Artifact | Purpose | State |
|---|---|---|
| [Pricing characterization](pricing-characterization.md) | Primary-MIP to fixed-LP convention and observed results | Executed candidate |
| [Runtime evidence](runtime-evidence.json) | Machine-readable identities, hashes, profile, and result summary | Executed candidate |
| [Gate checklist](gate-checklist.md) | Gate 1 criterion status | In progress |
| [Closure decision](closure-decision.md) | Formal blocker audit and Stage 2 authorization boundary | Hold recorded |
| [`tools.oracle`](../../tools/oracle/) | Class-based staged runner, fail-closed overlay, parsers, comparator, and CLI | Implemented and tested |
| [Objective fixture](../../tests/fixtures/oracle/vspd-v5.0.6-rtd-202502261155-dps-objectives.json) | Committed CPLEX objective values and provenance | Active smoke baseline |
| Canonical GDX/matrix evidence | Deterministic symbol, UEL, matrix, solution, and dictionary manifests | Two clean runs matched |
| Independent price validation | Bus-balance marginals mapped to nodes independently of vSPD price parameters | Passed for final-scenario snapshot |

## Qualified use of the current profiles

- `gams-scip-smoke` validates that pinned source, GDX input, preprocessing,
  MIP construction, and objective extraction execute at full scale.
- `gams-scip-highs-pricing` solves the MIP with SCIP, snapshots and fixes every
  binary/SOS variable, solves the resulting RMIP with HiGHS, restores original
  bounds, and exposes pricing marginals to the unchanged vSPD report logic.
- `gams-scip-highs-pricing` is the active adequate reference only when every
  required solve reports normal completion and optimal model status. CPLEX is
  deferred cross-validation.

Raw third-party inputs and generated reports remain outside Git. This directory
records their hashes and logical summaries pending legal/provenance approval.

Gate 2 production work is not authorized while the closure decision remains
`HOLD`. CPLEX is deferred and is not the cause of this hold.

## Reproduce the characterization profile

```bash
uv run python -m tools.oracle.cli run \
  --source /path/to/pinned-vspd-v5.0.6 \
  --input /path/to/case.gdx \
  --work-directory /new/empty/evidence-directory \
  --gams /path/to/gams \
  --profile scip-highs-pricing \
  --baseline tests/fixtures/oracle/vspd-v5.0.6-rtd-202502261155-dps-objectives.json
```

The work directory must not already contain `vspd`; the runner refuses to
overwrite staged evidence. For the fixed-pricing profile it also writes compact
canonical manifests, a Convert matrix validation, and an independent
node-price validation under `WORK_DIRECTORY/canonical/`. The command exits
non-zero unless operational solves, objective comparison, matrix checks, and
price checks all pass. Convert's expected `model status 14` export record is
classified separately and is not mistaken for an optimization failure.
