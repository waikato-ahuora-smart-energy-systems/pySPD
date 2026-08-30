# Gate 12 — End-to-end parity validation

| Field | Value |
|---|---|
| Gate | G12 — E2E parity validated |
| Status | **ACTIVE — HISTORICAL POPULATION ENUMERATION IN PROGRESS** |
| Applicable baselines | vSPD v5.0.6 at `21b1cf33…`; SPD v16 feature source at `84ed3c9…` |
| Entry | After Gate 10 for v5.0.6; after applicable Gate 11 work for a new formulation |
| Package manager | `uv` only |
| Strict profile | Historical pinned-vSPD compatibility solver/profile |
| Portable PySPD profile | Native PySCIPOpt SCIP MIP → fix all discrete/SOS state → HiGHS RMIP |
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

The first governed historical PySPD candidate prefix is complete. For
2022-11-06, all 196 canonical predecessor and affected cases completed under
the explicit SCIP-MIP → fixed-discrete → HiGHS-RMIP profile. The atomic
bundle contains the four affected identities in canonical order and all twelve
required surfaces for each identity (48 hash-verified surface files). Loading
the completed bundle through `CanonicalReplayBundleStore` reverified every
surface hash, and the bundle execution fingerprint exactly matched the frozen
runtime source at commit `3799b80`. The compact durable evidence index is
[`pyspd-replay-20221106.json`](pyspd-replay-20221106.json). This is candidate
execution evidence only; it becomes parity evidence after the corresponding
pinned-GAMS bundle is produced and compared.

The 2022-11-07 candidate prefix is now executing from the same frozen source.
Its governed plan contains 210 cases through the last of six affected
identities. The independent GAMS reference replay remains queued while the
historical population enumeration owns the single available GAMS network
licence node.

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
`3360a91ebd48f2e3cbb52a5e6766d893011054be`. Identity discovery uses
`dailymode = 0` for one narrowly defined reason: it forces the pinned RTD load
calculation that reveals the material shortfall which the defective daily path
suppresses by retaining stale input demand. This discovery profile is not a
daily-mode parity substitute. Every emitted identity must still be replayed
through the daily-mode state machine by GAMS and PySPD under `G12-02`.

The discovery profile uses SCIP for the primary MIP, limits execution to the
first historical shortfall decision, preserves the pinned model's exact
strict-positive branch, and records only a selected node-to-node transfer whose
source `EnergyShortfallMW` exceeds `1e-6 MW`. The threshold controls evidence
emission only; it does not alter the historical branch or the optimization.
The separation between discovery and daily-mode replay is governed by
[ADR-0013](../adr/0013-gate-12-shortfall-population-discovery.md).
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
qualifies that candidate calculation. It is not accepted as a population
checkpoint because it selected the historical `All` surface rather than the
exact canonical RTD surface. The replacement profile must reproduce those four
cases on the 270-case canonical RTD surface before population execution.

A corrected `dailymode = 1` benchmark on `Pricing_20230510.gdx` completed all
305 cases on the broad historical `All` surface with optimal primary and cleanup
solves and found zero thresholded material transfers, agreeing with the
diagnostic screen's zero candidates for that date. Its hash-bound result is retained in
[`historical-dailymode1-benchmark.json`](historical-dailymode1-benchmark.json),
but is invalidated even as trigger evidence because it both predates the exact
RTD-only execution profile (278 cases on that input) and changed the historical
strict-positive branch.

Two predecessor profiles are invalidated. The first applied the analytic
`1e-6 MW` threshold to the model decision itself and therefore changed the
historical state machine. The second preserved that branch but treated every
eligible-removal predicate—including GAMS `EPS` residues—as population
membership before proving a material transfer. It produced 737 identities on
only three dates, exceeding the declared 546-case population. The latter
failure and all supporting checkpoint hashes are retained in
[`historical-exact-positive-invalidation.json`](historical-exact-positive-invalidation.json).
The earlier single-date artifact is retained only as invalidated forensic
history; it is not qualifying trigger or population evidence.

The replacement profile passed its canonical qualification on
`Pricing_20221106.gdx`: all 270 selected RTD cases solved once in GDX order,
all operational solves were optimal, and exactly the four expected identities
and six node-to-node transfers were emitted. Identity, node, and displayed
quantity evidence exactly matches the independent algebraic reconstruction.
The source, overlay, listing, progress, transfer, checkpoint, and comparison
hashes are frozen in
[`historical-material-transfer-qualification.json`](historical-material-transfer-qualification.json).
This qualifies the discovery method for the 139-date enumeration; it does not
promote a one-date shard to the final population manifest.

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
The command retries only the observed transient GAMS network-licence session
error, by default up to six attempts separated by 300 seconds. Every other GAMS
failure remains immediate and fail-closed; the retry does not relax optimality,
case-order, artifact-hash, or checkpoint validation.
The network entitlement also requires GAMS to allocate local IPC ports. A
restricted sandbox that reports no available ports through `gamsprobe` produces
the same top-level licence message but cannot be repaired by waiting; licensed
enumeration must run in an execution context that permits that local IPC.

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

After the exact manifest has been emitted, materialize the governed replay
configurations with:

```bash
uv run --group gdx python -m tools.gate12.plan_affected_replays \
  --manifest /path/to/interval-identity-manifest.json \
  --inventory docs/gate-1/shortfall-input-inventory.json \
  --input-root /path/to/hash-bound/inputs \
  --system-directory /path/to/gams-system-directory \
  --output-directory /path/to/gate12-replay-plan
```

The command rechecks every source size and SHA-256 before loading canonical GDX
case order, then atomically writes the logical replay plan, 139 per-date PySPD
configurations, and a configuration-file hash index.

### Incremental replay and parity

Gate 12 no longer waits for the final population manifest before beginning
replay work. Under [ADR-0014](../adr/0014-incremental-gate-12-replay-parity.md),
`IncrementalDiscoveryFeed` consumes only the contiguous inventory-ordered
prefix of complete population checkpoints. Each checkpoint is re-bound to its
source GDX and converted into the canonical same-day prefix through the last
affected case.

Materialize currently available PySPD bundles once, or keep watching for new
discovery checkpoints:

```bash
uv run --group gdx python -m tools.gate12.materialize_incremental_pyspd \
  --discovery-checkpoints /path/to/gate12-work/checkpoints \
  --inventory docs/gate-1/shortfall-input-inventory.json \
  --input-root /path/to/hash-bound/inputs \
  --system-directory /path/to/gams-system-directory \
  --bundle-root /path/to/incremental/pyspd-bundles \
  --run-root /path/to/incremental/pyspd-runs \
  --watch
```

`--maximum-new-dates N` bounds work per pass without changing checkpoint
semantics. Each candidate bundle contains exactly the twelve required surfaces
for the affected cases, plus source, discovery-checkpoint, work-item, engine,
execution-source, and per-surface hashes. A complete existing bundle is
verified and reused; an incomplete run resumes after its last hash-verified
case checkpoint.

PySPD prepares and solves the prefix lazily, one case at a time. After every
accepted case it atomically checkpoints the exact predecessor generation,
event sequence, and unrounded publication numerators and seconds. For affected
cases it also renders and hash-addresses the eleven surfaces that do not depend
on end-of-day publication while the Pyomo model is still live. The solved model
is then released. At prefix completion, the accumulator produces the rounded
published prices and completes the twelfth surface plus the corresponding
report rows. The final date bundle remains atomic. Resume rejects a changed
source, work item, application configuration, execution source, case prefix,
or any missing or modified partial surface; uncheckpointed work is repeated
rather than inferred. The candidate execution fingerprint covers
`pyproject.toml`, `uv.lock`, and every Python file under `src/pyspd`,
`tools/gate12`, and `tools/oracle`. The reference fingerprint additionally
covers the pinned GAMS source programs and GAMS executable bytes.

The first live candidate-prefix rehearsal failed closed at historical case
`51012022111105693`, exposing a native SCIP LP error under an over-tightened
`1e-9` feasibility setting. The same isolated case completes with SCIP's
explicit `1e-6` setting. The portable profile separately projects only SOS
members within `1e-5` of zero or one to their exact boundary before fixing the
HiGHS RMIP; the complete unit and probity suite validates this state transfer.
The first bounded prefix rehearsal also exposed a quadratic branch-endpoint
scan in post-solve observation projection. That projection now builds indexed
node, offer, bus, branch, and flow maps once per case; the formerly failing
historical case completes end to end in 65.69 seconds on the qualification
host with the indexed path.

Materialize the independent pinned-GAMS bundles with the same discovery feed:

```bash
uv run --group gdx python -m tools.gate12.materialize_incremental_gams \
  --discovery-checkpoints /path/to/gate12-work/checkpoints \
  --inventory docs/gate-1/shortfall-input-inventory.json \
  --input-root /path/to/hash-bound/inputs \
  --system-directory /path/to/gams-system-directory \
  --source-tree /path/to/pinned/vspd-v5.0.2 \
  --gams-executable /path/to/gams \
  --bundle-root /path/to/incremental/gams-bundles \
  --run-root /path/to/incremental/gams-runs \
  --maximum-new-dates 1
```

The reference overlay retains each failed attempt separately, requires daily
mode and the exact same-day prefix, and uses the qualified GAMS SCIP MIP to
fixed-discrete HiGHS RMIP profile. Its observational cumulative GDX captures
raw and repaired bus prices separately, accepted physics and objectives,
shortfall transitions, solve counts, native discrete/SOS state, publication
weights and outputs, and the ordinary vSPD CSV reports. A bundle is emitted
only after every operational solve is optimal and the existing independent
matrix/price checks pass. With the observed single-node network entitlement,
this command must wait while historical population enumeration owns the GAMS
session.

When both canonical bundles for a date are available, compare and checkpoint
all available dates with:

```bash
uv run --group gdx python -m tools.gate12.compare_incremental_replays \
  --discovery-checkpoints /path/to/gate12-work/checkpoints \
  --inventory docs/gate-1/shortfall-input-inventory.json \
  --input-root /path/to/hash-bound/inputs \
  --system-directory /path/to/gams-system-directory \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --parity-checkpoints /path/to/incremental/parity-checkpoints
```

The initial comparator is exact canonical JSON byte parity. It is intentionally
strict: every changed surface becomes an unresolved discrepancy. Its
observation mode checkpoints every currently paired date instead of stopping at
the first mismatch, then exits nonzero when any date failed. An unchanged
failed checkpoint is reusable as failed evidence so later dates can continue to
be compared; it is never reusable as a pass. A later tolerance or
degeneracy-aware comparator must use a separately named processor profile and
retain its case-specific evidence. Incremental success does not relax the final
requirement for exactly 546 identities across all 139 dates.

For every paired date, preserve a quantified path-level diff alongside the
exact parity checkpoint:

```bash
uv run --group gdx python -m tools.gate12.quantify_canonical_replay \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --trading-date 20221106 \
  --output /path/to/incremental/quantified-diffs/20221106.json
```

This immutable artifact retains every missing, extra, and changed canonical
JSON leaf with its path and both values. Hexadecimal floating-point leaves are
also compared numerically, with per-surface and per-date maximum absolute
errors. It is diagnostic evidence: it does not apply a tolerance, certify a
solver-sensitive alternative, or convert a discrepancy into a pass.

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

`E2ECaseEvidenceBuilder` accepts canonical bytes for exactly the twelve required
case surfaces and hashes each independently; duplicates or omissions fail.
`PyspdCaseSurfaceExporter` now projects every completed PySPD case onto those
exact surfaces using deterministic hexadecimal floating-point values. It keeps
selection, state transitions, primary physics and objective, fixed-discrete and
native-SOS pricing state, raw/repaired/node/reserve prices, publication inputs,
rounded outputs, and case-filtered report fields independently hashable.
`E2EDayEvidenceBuilder` separately hashes canonical order, original output,
repeat output, resumed output, and reports, leaving repeat/resume drift visible
to the closure validator rather than collapsing the artifacts early.
`DiscrepancyRegister` assigns every delta a unique case/surface/identity key and
requires resolution text and a SHA-256 evidence artifact as a pair. Its closure
check rejects any material record that remains unresolved.

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
