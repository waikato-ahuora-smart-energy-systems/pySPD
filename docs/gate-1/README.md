# Gate 1 — executable oracle and corpus

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Started | 29 August 2026 |
| Current decision | **HOLD — NOT CLOSED; SCIP/HiGHS ACTIVE REFERENCE** |
| Compatibility source | vSPD v5.0.6, commit `21b1cf33f5607399331dcb1c03270348def5ccc8` |
| Initial executed case | `RTD_202502261155_251012025022255930_20250226115400` |

Gate 1 characterization continues under the Gate 0 research authorization.
ADR-0008 treats the optimal SCIP-MIP plus fixed-discrete HiGHS-RMIP pathway as
adequate for current development. This is not permission to claim CPLEX parity;
the 2023/2025 pack classification, a ten-run RTD/PRSS/AUD corpus, and calibrated
matrix/price checks are now complete. Preprocessing checkpoints, complete
pre/post solve-state pairs, and an observational-neutrality control are also
complete. Per-invocation semantic matrix/name dictionaries are also retained.
The versioned Stage 4--7 projection map, ranged/sign transforms, dual-side
rules, and complementarity thresholds are frozen and analytically tested. The
separate 546-interval population remains open. ADR-0009 removes independent review as a Gate 1
requirement.

## Current evidence

| Artifact | Purpose | State |
|---|---|---|
| [Pricing characterization](pricing-characterization.md) | Primary-MIP to fixed-LP convention and observed results | Executed candidate |
| [SPD/AUD characterization](spd-aud-characterization.md) | Fail-closed mode overlays, report inventory, matrix and independent-price evidence | Executed sample |
| [Corpus characterization](corpus-characterization.md) | Hash-bound 2023/2025 classification, ten frozen runs, and official comparisons | Executed corpus |
| [Corpus manifest](corpus-manifest.json) | Pack Git-tree/input hashes and external evidence hashes | Frozen |
| [Comparator specification](comparator-specification.md) | Canonical KKT equations, scales, thresholds, and price-transfer mapping | Frozen for current full-matrix checks |
| [Runtime evidence](runtime-evidence.json) | Machine-readable identities, hashes, profile, and result summary | Executed candidate |
| [Instrumentation-neutrality evidence](instrumentation-neutrality.json) | Hash-bound checkpoint/control equivalence proof | Passed |
| [Incremental matrix mappings](incremental-matrix-mappings.json) | Exact Stage 4--7 family ownership and permitted transformations | Frozen v1 |
| [Basis sensitivity](basis-sensitivity.json) | Alternative optimal fixed-RMIP primal/dual classification | Classified |
| [Reference performance](reference-performance.json) | Controlled phase/wall/RSS baseline | Recorded |
| [Shortfall date population](shortfall-transfer-population.json) | Authority-declared 546 intervals across 139 dates | All daily inputs acquired; exact interval IDs not publicly disclosed |
| [Shortfall input inventory](shortfall-input-inventory.json) | Individual hashes for all 139 official daily GDX files | Acquired and frozen |
| [Shortfall characterization](shortfall-characterization.json) | Optimal affected-path fixture and rejected relaxed selector | Blocker classified |
| [Gate checklist](gate-checklist.md) | Gate 1 criterion status | In progress |
| [Closure decision](closure-decision.md) | Formal blocker audit and Stage 2 authorization boundary | Hold recorded |
| [`tools.oracle`](../../tools/oracle/) | Class-based staged runner, fail-closed overlay, parsers, comparator, and CLI | Implemented and tested |
| [Objective fixture](../../tests/fixtures/oracle/vspd-v5.0.6-rtd-202502261155-dps-objectives.json) | Committed CPLEX objective values and provenance | Active smoke baseline |
| Canonical GDX/matrix evidence | Deterministic symbol, UEL, matrix, solution, and dictionary manifests | Passed for all ten frozen runs |
| Independent price validation | Marginals and raw transfer graph mapped independently of vSPD node-price parameters | Passed for 20,344 corpus prices, including 38 transfers |

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
  --run-name gate1_spd_rtd_202502261155 \
  --operation-mode SPD \
  --baseline tests/fixtures/oracle/vspd-v5.0.6-rtd-202502261155-dps-objectives.json
```

The work directory must not already contain `vspd`; the runner refuses to
overwrite staged evidence. For the fixed-pricing profile it also writes compact
canonical manifests, a Convert matrix validation, and an independent
node-price validation under `WORK_DIRECTORY/canonical/`. The command exits
non-zero unless operational solves, objective comparison, matrix checks, and
price checks all pass. Convert's expected `model status 14` export record is
classified separately and is not mistaken for an optimization failure.

Use `--no-state-evidence` only for a controlled neutrality run. Compare it with
the ordinary instrumented evidence using `compare-neutrality`; the comparator
fails closed on any economic, report, solve-record, price, matrix, solution,
dictionary, configuration, or validation difference.

Use `--daily-mode 0` and repeat `--case-id` for an exact, hash-bound
recomputed-demand fixture. `tools.oracle.population` acquires the governed
139-date population with `uv`, atomically retains raw GDX files outside Git,
and emits the committed date/size/SHA-256 inventory.
