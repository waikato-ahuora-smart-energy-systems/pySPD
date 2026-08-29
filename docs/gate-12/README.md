# Gate 12 — End-to-end parity validation

| Field | Value |
|---|---|
| Gate | G12 — E2E parity validated |
| Status | **PLANNED — MANDATORY PARITY DEBT REGISTERED** |
| Applicable baselines | vSPD v5.0.6 at `21b1cf33…`; SPD v16 feature source at `84ed3c9…` |
| Entry | After Gate 10 for v5.0.6; after applicable Gate 11 work for a new formulation |
| Package manager | `uv` only |
| Strict profile | Historical pinned-vSPD compatibility solver/profile |
| Portable profile | GAMS-SCIP primary MIP → fix all discrete → HiGHS RMIP |
| Human approval | No separate independent reviewer required under project direction |

The live criterion register is in [`gate-checklist.md`](gate-checklist.md).

Gate 12 owns the exact end-to-end validation intentionally removed from the
amended Gate 8 boundary. It does not reopen or duplicate the Stage 8
implementation. It proves the complete observable chain from immutable raw GDX
through selection, preprocessing, overrides, every solve and re-solve, accepted
physics, fixed-discrete pricing, price repair, publication, and reports.

## Inherited parity debt

| Obligation | Gate 8 evidence | Gate 12 completion condition |
|---|---|---|
| Affected interval identities | 427 Gate 8 candidates; Gate 12 algebraic screen now 434 candidates | Exactly 546 unique case IDs, leaving zero unidentified intervals |
| Shortfall behavior | Exact affected fixture plus bounded analytic state-machine coverage | All 546 cases replayed against pinned GAMS and PySPD |
| Whole-day behavior | Representative single case | Complete representative normal, feature-rich, outage, 46-period, and 50-period days |
| Official energy prices | Identity set exact; max difference `1.23576` NZD/MWh | Strict-profile parity or case-specific degeneracy certificate |
| Official reserve prices | Identity set exact; max difference `0.0746` NZD/MWh | Strict-profile parity or case-specific degeneracy certificate |
| Reports | Stage 8 price/publication surfaces | Every Gate 9 in-scope report and field compared end to end |
| Repeat/resume | Analytic checkpoint contract | Repeated and resumed whole-day equality |

## Gate 11 v16 parity debt

| Obligation | Gate 11 evidence | Gate 12 completion condition |
|---|---|---|
| Representative RTD objective | Pyomo exceeds feature oracle by approximately `7.8328185` | Explain and eliminate the algebraic difference, or reject the compatibility claim |
| Reserve prices | Both pathways are optimal but published reserve prices differ | Strict comparison plus finite-difference/basis classification |
| PRSS | Schema and eight-interval selection characterized | Full solve, performance, prices, and reports |
| NRSS | Schema characterized; orchestration unsupported | Add and qualify an explicit profile if included in the declared scope |
| CPLEX | Deferred by project direction | Execute the strict profile before a CPLEX-based claim |
| Formulation/source safeguard | PDF battery ambiguity rule differs from demonstrable feature-source behavior | Record the governing decision and compare its observable effect |

## Current execution evidence

The representative v16 RTD portable-profile run is recorded in
[`v16-representative-parity.json`](v16-representative-parity.json). Both the
SCIP primary solve and the fixed-discrete HiGHS pricing solve report optimal,
the independent validator passes, and the objective differs from the pinned
GAMS oracle by only `4.56e-06`. Reserve-price comparison passes: three values
match directly and the NI FIR alternative (`0.01` versus `0.11` NZD/MWh) has a
two-sided perturbation certificate showing both values on the local optimal
cost kink.

This evidence does **not** close v16 parity. Of 567 node energy prices, 389
remain materially different, with a maximum absolute difference of
`0.743824` NZD/MWh. The pinned GAMS run fixes its native SOS member state for
pricing, while the portable Pyomo formulation fixes an equivalent
adjacent-interval binary state. Their common objective is established, but a
common-optimal-face or per-observable price certificate has not yet been
produced. Pyomo's GAMS writer also rejects an active `SOSConstraint`, so the
native-SOS qualification profile cannot currently be exported through that
backend. These are held as explicit Gate 12 debt rather than being inferred
away from the objective match.

The v5 affected-population evidence is likewise incomplete. Gate 12 has now
replayed the first-loop RTD load equations against every hash-bound input and
identified 434 diagnostic candidates, seven more than the Gate 8 screen. The
numerical gap to the declared count is 112, but candidate membership is not
treated as an affected-case proof. The screen correctly refuses to emit an
exact manifest. Its compact evidence is
[`analytic-population-lower-bound.json`](analytic-population-lower-bound.json).
Exact population qualification therefore remains with the solved historical
v5.0.2 shortfall-transfer oracle.

## Historical population execution

The population oracle is pinned to vSPD v5.0.2 commit
`3360a91ebd48f2e3cbb52a5e6766d893011054be`. It retains `dailymode = 1`, because
the Authority's 546-interval disclosure is specifically the daily-mode RTD
defect, uses SCIP for the primary MIP, limits discovery to the first historical
shortfall decision, and records only shortfalls above `1e-6 MW`.
The source overlay is fail-closed and hash-addressed; unexpected upstream text
does not get silently patched.

`HistoricalPopulationRunner` verifies every Gate 1 source size and SHA-256,
reads the GDX run-mode surface, selects exactly RTD modes 101 and 201, and
accepts a daily checkpoint only when the progress identities are exact, every
selected case is solved once in canonical GDX order with an optimal primary
solve, all cleanup solves are optimal, and the emitted node evidence is a
subset of the selected cases. Lexically sorted or otherwise permuted progress
is rejected even when membership is identical. Each atomic
checkpoint binds the raw listing, progress, and evidence hashes as well as the
source, patch, and solver profile. Resume skips only a fully matching
checkpoint. `HistoricalAffectedManifestBuilder` then refuses to emit the final
manifest unless it contains exactly 546 unique identities across all 139 source
hashes.

An earlier `dailymode = 0` full-day rehearsal on `Pricing_20221106.gdx`
completed 278 optimal primary solves and 11 optimal cleanup solves. Its four
cases and six node values exactly agree with the algebraic reconstructor, which
qualifies that candidate calculation, but the run is explicitly rejected as
evidence for the Authority-disclosed daily-mode population. A new workspace and
profile are required for all accepted population checkpoints.

A corrected `dailymode = 1` benchmark on `Pricing_20230510.gdx` completed all
305 cases on the broad historical `All` surface with optimal primary and cleanup
solves and found zero material transfers, agreeing with the diagnostic screen's
zero candidates for that date. Its hash-bound result is retained in
[`historical-dailymode1-benchmark.json`](historical-dailymode1-benchmark.json),
but is excluded from population qualification because it predates the exact
RTD-only execution profile (278 cases on that input).

Run or resume the governed enumeration with `uv`:

```bash
uv run --group gdx python -m tools.gate12.enumerate_historical \
  --source-tree /path/to/clean/vspd-v5.0.2 \
  --work-directory /path/to/gate12-work \
  --input-root /path/to/hash-bound/inputs \
  --inventory docs/gate-1/shortfall-input-inventory.json \
  --gams-executable /path/to/gams \
  --system-directory /path/to/gams-system-directory
```

The command produces per-date checkpoints, `population-summary.json`, and—only
after the exact declared population is proven—`interval-identity-manifest.json`.

`ApplicationConfiguration.case_ids` is the governed PySPD replay selector. The
ordered identity list is included in the configuration hash; duplicates, blank
identities, and any requested identity absent from the source selection surface
fail before a solve. An empty tuple remains the explicit complete-day selection.
The same configuration explicitly names and hashes
`scip-mip-fixed-highs-rmip`; an unregistered or opportunistically substituted
solver profile fails before execution. The complete application-configuration
hash—including ordered case selection and solver profile—is carried into the
daily-run hash and therefore into result, checkpoint, and report provenance.
An isolated affected case is diagnostic only because it can omit prior accepted
dispatch. `HistoricalAffectedReplayPlanner` therefore builds a hash-addressed,
canonical same-day prefix through the final affected case on every date. It
requires all 546 globally unique affected case IDs, all 139 source hashes, exact
date-time/trading-period membership, and every predecessor needed to reproduce
daily initialization.

For isolated partial inventories, pass `--execution-scope shard`. A complete
shard then exits successfully and records `shard_complete: true`, while
`population_passed` remains false and no interval manifest can be emitted.
Plan deterministic balanced inventories with `plan_historical_shards`, execute
each in a separate work directory, and combine them only through
`merge_historical_shards`. The merger requires exactly one provenance-valid
checkpoint for every one of the 139 governed dates before applying the same
546-identity manifest gate. The currently installed network entitlement was
observed to permit one active enumeration session, so local shards are executed
serially; this affects elapsed time, not evidence semantics.

## Required evidence pack

- `interval-identity-manifest.json`: exactly 546 identities, each bound to one
  of the 139 Gate 1 source hashes and a discovery rationale;
- per-interval state-transition comparisons for pinned GAMS and PySPD;
- full-day manifests for ordinary, defect, feature-rich, and daylight-saving
  dates;
- primary/pricing structural fingerprints and accepted solution hashes;
- raw, repaired, node, reserve, weighted, rounded, and report-field diffs;
- common-optimal-face, finite-difference, KKT, and basis evidence for any
  claimed solver-sensitive price;
- deterministic repeat and checkpoint/resume comparisons;
- strict-profile and portable-profile result summaries kept separate; and
- a discrepancy register with zero unresolved material entries at closure.

## Fail-closed rules

- A date list is not an interval-identity manifest.
- A relaxed solve cannot enumerate the population because Gate 1 observed a
  false negative.
- An objective match does not prove price or report parity.
- A portable-profile solver difference cannot be labeled strict compatibility.
- Missing identities, stale solve state, incomplete full days, or unexplained
  material prices hold Gate 12.
- Gate 8 closure cannot be used as substitute evidence for any Gate 12 item.

The authoritative work and pass criteria are in
[`Stage 12 — End-to-end parity validation`](../pyomo-vspd-stage-gate-plan.md#stage-12--end-to-end-parity-validation).
