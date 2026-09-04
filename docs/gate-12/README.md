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
The ten-day CPLEX corpus and the full designated-day SCIP→HiGHS and SCIP→CLP
comparison are documented in the
[`CPLEX reference corpus validation`](cplex-reference-corpus-validation.md).
Both tested pathways are complete and optimal, but neither establishes exact
CPLEX parity; SCIP→HiGHS remains the overall-fidelity default.
Four additional SCIP→HiGHS full-day runs are documented in the
[`expanded CPLEX analysis`](cplex-reference-expanded-four-days.md).
The two remaining 2023-09-22 TP1 SI reserve publications are retained as a
fail-closed historical residue after same-matrix CPLEX, native `solvefinal`,
reserve-zone, two-sided derivative, algorithm, and daily-mode diagnostics. See
the [`TP1 reserve-price residue`](cplex-tp1-reserve-residue-20230922.md).

TP24's alternate TUI generation is independently certified as a 3.486 MW
redistribution between equal-price 210.07 NZD/MWh blocks across a lossless,
unconstrained transformer star. The certificate admits only the fourteen
directly affected offer, bus, branch, and daily-node identities; see the
[`TP24 equal-price allocation`](cplex-tp24-energy-allocation-20230922.md).

The cross-corpus treatment of basis-dependent passive zero-flow prices is in
the [`ten-day CPLEX zero-flow analysis`](cplex-zero-flow-analysis-ten-days.md).
The distinct 2023-09-22 TP4 reserve-loss breakpoint diagnosis and bounded
primal canonicalization are in the
[`TP4 reserve-kink certificate`](cplex-tp4-reserve-kink-20230922.md).
The 2023-11-24 ARG1101 diagnosis proves a second basis-dependent boundary:
fresh CPLEX reproduces HiGHS on the same fixed LP, while only CPLEX's
MIP-to-fixed-LP continuation reproduces the archived marginal. See the
[`TP29 canonical-matrix diagnosis`](cplex-tp29-mip-basis-diagnosis-20231124.md).
The corrected 297-case 2023-11-24 evidence also reproduces TP16 ABY0111
exactly at 158.78761 NZD/MWh after restoring vSPD's daily transfer guard,
persistent disconnected-bus state, and unresolved-dead-node bus-report rule.
Its complete-day evidence is bound by
[`cplex-reference-paths-20231124-highs-corrected.json`](cplex-reference-paths-20231124-highs-corrected.json)
and
[`cplex-reference-comparison-20231124-highs-corrected.json`](cplex-reference-comparison-20231124-highs-corrected.json).
For 2023-09-22, the passive-tree replay now covers all 274 cases across all 48
trading periods, with every SCIP MIP and HiGHS fixed-RMIP solve optimal.
Forty-seven periods have zero unresolved published-energy differences; all 167
remaining rows are confined to TP4. Weighted analytic intervals
are preserved through solver-path serialization and stream aggregation, while
the governed scalar remains the export endpoint. A passive singleton with
multiple live boundaries now retains its solver scalar and exposes only the
non-empty intersection of its boundary intervals; this certifies TP12
ATU1101 without selecting a CPLEX-specific value. The same construction
handles TP1's passive ARI transformer tree because its two live parallel
boundaries meet at one root. See the
[`progressive validation record`](cplex-reference-passive-tree-progress-20230922.md)
for the current boundary and remaining complete-day obligation.

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

The first governed historical PySPD candidate prefix and paired GAMS reference
are complete. For 2022-11-06, all 196 canonical predecessor and affected cases
completed under the explicit SCIP-MIP → fixed-discrete → HiGHS-RMIP profile.
The post-WPT replacement bundles contain the four affected identities in
canonical order and all twelve required surfaces per identity. They are bound
to candidate hash
`6b01efdf84eacfac717a47df9927482316288e0b7ab2ccc5c645a1ed25ef1f71`
and governed two-objective GAMS bundle hash
`e824a75c89939ea250e0a63d81b75cd0bac81c613aadda6dcb07be4fa0a066f0`.
Superseded bundles and validator outputs remain immutable diagnostic evidence;
they are not rewritten.

The refreshed exact processor reports 36 changed surfaces and 1,119,849 changed
paths. Most are sparse-zero or report-schema representation differences. The
semantic processor compares active SOS support, applies the established
`1e-4` price/objective tolerance and `1e-8` physics/fixed-state tolerance, and
retains the SCIP primary objective as a named diagnostic while requiring the
fixed-HiGHS objective to pass. With the independent zero-flow convention
certificate, it leaves only four unresolved `report-field` schema records—one
per affected case—and zero unresolved numeric price differences.

The older compact semantic index remains immutable pre-correction evidence.
The refreshed hashes and disposition are recorded in the
[`post-WPT rerun certificate`](post-wpt-rerun-certification-20221106.md).

The older source-allocation null-space certificate correctly rejects the final
case because its `KIN1009` delta is observable. The stronger independent
source-topology certificate proves the two one-sided derivatives instead. It
certifies 58 bus prices, projects `KIN1009` with zero residual, and exactly
reconstructs TP15 `KIN1009`, TP35 `KIN1009`, and TP35 `WPT1101` publications.
Its compact index is
[`zero-flow-price-convention-20221106.json`](zero-flow-price-convention-20221106.json).

The separately governed Authority-to-PySPD schema crosswalk now resolves all
142 Authority fields across all 13 tables for each of the four affected cases.
Candidate-only audit and diagnostic fields are explicitly governed supplements,
not accidental omissions. The earlier incomplete crosswalk remains immutable
as [`report-crosswalk-20221106.json`](report-crosswalk-20221106.json); the
replacement hashes are recorded in the completion certificate below.

The final provenance-clean 196-case candidate bundle adds complete class-based
report projectors without changing the governed v5 optimization structure. The
mapped comparison passes all 13 tables and 68,558 values: zero missing or extra
identities, zero above-tolerance values, and zero unimplemented tables. Its 257
classified values comprise independently certified zero-flow prices, branch
endpoint prices within the approved portable raw-price tolerance, and
nonnegative alternative offer-reserve allocations whose aggregate survives
Authority rounding under [ADR-0017](../adr/0017-portable-report-equivalence.md).
The hash-bound row result is accepted by the semantic
validator, which passes all twelve canonical surfaces with zero unresolved
differences. The complete first-date result is recorded in
[`report-completeness-20221106.md`](report-completeness-20221106.md).

The second paired date, 2023-01-17, also passes. Both engines completed its
191-case prefix, and the one affected case passes all twelve semantic surfaces
with zero unresolved differences. The independent topology validator certifies
49 zero-flow bus derivatives, three node projections, and three TP34
publications. The complete 13-table comparison covers 17,203 values with zero
missing or extra identities, zero above-precision values, and zero
unimplemented tables. See the
[`2023-01-17 replay certificate`](replay-certification-20230117.md).

The third paired date, 2023-01-18, passes after correcting the application
solve to use native SCIP SOS2 state. Both engines completed its 190-case prefix,
and all four affected cases pass all twelve semantic surfaces with zero
unresolved differences. The independent topology validator certifies 190 bus
observations, seven node projections, and two TP33 publications. The complete
13-table comparison covers 68,516 values with zero missing or extra identities,
zero above-precision values, and zero unimplemented tables. A common
`152.41571 NZD/MWh` dual total placed on different simultaneously binding
SFD22 constraint rows is certified under
[ADR-0020](../adr/0020-binding-market-node-dual-allocation.md). See the
[`2023-01-18 replay certificate`](replay-certification-20230118.md).

The fourth paired date, 2023-01-16, passes all 96 semantic surfaces across its
eight affected cases. Both engines completed the 109-case prefix, and the
largest fixed-RMIP objective difference is `2.09e-9 NZD`. The independent
topology validator certifies 448 zero-flow bus observations, 41 node
projections, and ten TP16/TP18 publications. The complete 13-table comparison
covers 137,394 values with zero missing or extra identities, zero
above-precision values, and zero unimplemented tables. The date also adds the
bounded native-SCIP SOS residue rule governed by
[ADR-0021](../adr/0021-bounded-scip-sos-support-residue.md). See the
[`2023-01-16 replay certificate`](replay-certification-20230116.md).

The fifth paired date, 2022-11-07, passes all 72 semantic surfaces across its
six affected cases after the complete 210-case prefix. The largest fixed-RMIP
objective difference is `5.61e-10 NZD`. The independent topology validator
certifies 348 zero-flow bus observations, 22 node projections, and seven
publications. The complete 13-table comparison covers 102,571 values with zero
missing or extra identities, zero above-precision values, and zero
unimplemented tables. The replay also corrects dynamic scarcity reconstruction
when a zero-load node receives transferred load. Bounded transition and
non-binding report equivalence is governed by
[ADR-0022](../adr/0022-portable-transition-and-nonbinding-report-equivalence.md).
See the [`2022-11-07 replay certificate`](replay-certification-20221107.md).

Further replay continues incrementally from exact historical discovery.
Candidate execution never promotes an analytic lower bound into an affected
identity. The complete 2022-11-06 and 2023-01-17 prefixes have both passed
regression under the native-SOS execution fingerprint; see
[`native-sos-regression-20221106.md`](native-sos-regression-20221106.md) and
[`native-sos-regression-20230117.md`](native-sos-regression-20230117.md).
Together with the 2022-11-07, 2023-01-16, and 2023-01-18 correction
certificates, all five paired dates now pass their recorded native-SOS
execution profiles. Existing
immutable certificates remain valid for their recorded profiles.

An optional native-SCIP to fixed-CLP validation pathway has also been
implemented without changing the qualified default. Its hash-bound WPT1101
trial matches the fixed-RMIP objective within `2.70e-8 NZD` and reconstructed
node prices within `2.84e-14 NZD/MWh`. CLP selects materially different raw
duals on a degenerate zero-flow face, so it remains an independent validation
profile rather than a certified replacement. See the
[`full-day four-path benchmark`](four-solver-path-benchmark-20221106.md) and
the
[`SCIP-to-CLP validation trial`](scip-clp-validation-trial-20221106.md).

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

The governed default-tolerance enumeration completed five atomic dates, but
on 2022-11-24 23:00 it repeatedly returned a SCIP optimum whose scaled solution
violated the original `OAM_T1.T1` branch-block row by
`0.00034560206410994 MW`. GAMS rejected that solution and remained in
post-solve processing. The five completed checkpoints remain qualifying and
immutable for their dates; that failed 2022-11-24 attempt contributed no
checkpoint and was superseded by the separately hashed successful recovery
below. Global `numerics/feastol` calibrations at `1e-9` and `1e-10` are
nonqualifying: both still produced GAMS-rejected original-model residuals
(about `1.22e-7` and `1.26e-7`), while `1e-10` was too slow for population use.
The 2022-11-24 recovery is therefore narrow and separately hash-addressed. A
case-only `1e-10` trial reduced the rejected residual to
`3.9538568300155e-8` but did not clear GAMS. `1e-11` and `1e-12` trials could
instead terminate with SCIP LP numerical failure. The qualifying recovery
keeps the stable target-only `1e-10` constraint tolerance and sets
`numerics/checkfeastolfac = 1e-4`, without broad numerical emphasis. It clears
only sub-`1e-6 MW` adjustments in the two named mixed material/residue cases
and skips residue-only loops when no material evidence could be emitted.

The complete atomic shard passed: 261/261 selected cases were exact and
optimal. It discovered two first-loop transfers, both `ABY0111 -> TIM1101`:
`2.259244594868 MW` at 23:00 and `0.204906717115 MW` at 23:05. The checkpoint
logical hash is
`fa975ac86c2e32a8bde72d904fb8b0d016ebe7811cb67795d7dd1dc939c323ed`;
the compact durable record is
[`historical-targeted-recovery-20221124.json`](historical-targeted-recovery-20221124.json).
All other cases retain the qualified default SCIP profile. Run the isolated
recovery with:

```bash
uv run --group gdx python -m tools.gate12.enumerate_historical \
  --source-tree /path/to/clean/vspd-v5.0.2 \
  --work-directory /path/to/targeted-20221124-work \
  --input-root /path/to/hash-bound/inputs \
  --inventory /path/to/one-date-20221124-inventory.json \
  --gams-executable /path/to/gams \
  --system-directory /path/to/gams-system-directory \
  --execution-scope shard \
  --tight-scip-case-id 241012022111000704 \
  --tight-scip-feastol 1e-10 \
  --tight-scip-checkfeastolfac 1e-4 \
  --material-only-shortfall-case-id 241012022111000704 \
  --material-only-shortfall-case-id 241012022111005708 \
  --suppress-residue-only-shortfall-loops
```

This command makes only a one-date shard claim. The two identities may enter
the final population builder, but the shard does not make the 139-date or
546-identity population claim and does not rewrite the five default-profile
checkpoints.

The next chronological date demonstrated that subthreshold removal margins
are a recurrent discovery-liveness issue, including as companions to material
transfers. ADR-0016 therefore permits a separate three-file overlay that clears
only adjustments whose own source shortfall is at or below `1e-6 MW`
immediately before the discovery transfer loop. It does not create a SCIP
option file and retains every material adjustment. The 2022-11-25 shard passed
282/282 exact optimal selected cases and preserved five affected identities;
its checkpoint logical hash is
`a9c993352f8ddef9f47933d0276ff7414cb922e26a0acd393ca82e7553deb8c7`.
The compact record is
[`historical-residue-recovery-20221125.json`](historical-residue-recovery-20221125.json).
Run this profile with `--suppress-residue-only-shortfall-loops` and no targeted
SCIP arguments.

The same qualified profile then passed the next chronological date,
2022-12-04: 274/274 exact optimal selected cases and one first-loop transfer,
`WVY0111 -> WVY1101` at 09:00 for `2.025482396568 MW`. Its checkpoint logical
hash is
`c15fc962a45247766d27ae93bc2e5d3db5a295e1748ec25b786021640b88627e`;
the compact record is
[`historical-residue-recovery-20221204.json`](historical-residue-recovery-20221204.json).

The 2023-01-16 shard also passed: 283/283 exact optimal cases and eight
material identities. Its logical checkpoint hash is `ffb4258c067407fd5b3b61f4870f9f90dfa9c928c210dc2f7cfaccb143966fea`;
see [`historical-residue-recovery-20230116.json`](historical-residue-recovery-20230116.json).

The next chronological shard, 2023-01-17, passed 271/271 exact optimal cases
under the same residue-guard profile and emitted one material identity:
`KMO0331 -> KMO1102` at 16:55 for `2.094803183992 MW`. Its logical checkpoint
hash is `1bcfed2d989a8d23e1b30a361a985c99dd809f508f25c7abf532f5d6711e83a3`;
see [`historical-residue-recovery-20230117.json`](historical-residue-recovery-20230117.json).

The 2023-01-18 shard passed 277/277 exact optimal cases and emitted four
material `CLH0111 -> CLH0661` identities from 16:10 through 16:25. Its logical
checkpoint hash is `a5cab808d5864b50fa4250ec71c1b9a6f2b115a1781d550e2172d4b892b9174c`;
see [`historical-residue-recovery-20230118.json`](historical-residue-recovery-20230118.json).

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
explicit `1e-6` setting. The portable profile separately projects SOS members
within `1e-5` of zero or one to their exact boundary, fixes only inactive
zero-valued members, and leaves active interpolation weights continuous for
the HiGHS RMIP. The portable interval binaries preserve the selected SOS
support; the complete unit and probity suite validates this state transfer.
The first bounded prefix rehearsal also exposed a quadratic branch-endpoint
scan in post-solve observation projection. That projection now builds indexed
node, offer, bus, branch, and flow maps once per case; the formerly failing
historical case completes end to end in 65.69 seconds on the qualification
host with the indexed path.

The first paired daily comparison then exposed a mode-boundary defect: PySPD
was applying RTD required-load reconstruction in daily mode, while pinned
`vSPDsolve.gms` applies that calculation only when `dailymode = 0`. This caused
four false PySPD shortfall transfers and second solves on 2022-11-06. Daily
preparation now retains source demand, matching the pinned control flow; the
non-daily reconstruction remains enabled for population discovery and its
direct qualification tests. A scaling-disable-only shortfall check likewise
does not trigger a daily re-solve, because the disabled RTD scaling calculation
is absent from daily mode.

The corrected first-date comparison also exposed a solver-tolerance artifact in
the final affected interval. SCIP could return a nominally nonnegative balance
violation about `1.6e-7 MW` below zero. With vSPD's `1,000,000 NZD/MW` penalty,
that physically tiny bound residue moved the raw primary objective by about
`0.16 NZD`, and repeated SCIP runs could select different residues within the
same tolerance. Full-prefix trials at `1e-9` and `1e-8` were rejected because
SCIP's internal LP solver failed on cases 2 and 68 respectively. The stable
`1e-6` primary profile is therefore retained. The objective surface now keeps
the raw SCIP MIP objective and the fixed-discrete HiGHS RMIP objective as
separate values; the latter is the feasibility-refined economic parity value,
while the former remains diagnostic evidence and is never silently replaced.
Accepted dispatch, shortfall, flow-derived reporting, and daily predecessor
state likewise come from the fixed RMIP, matching the levels pinned vSPD leaves
after `solveFinal`; the raw SCIP primal snapshot remains immutable in the solve
payload for diagnostics.
The original exact failed checkpoint and both tighter-tolerance failed progress
roots are retained.

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
matrix/price checks pass. For a multi-case daily prefix, the independent price
validator checks every raw nodal price against the balance marginals and node
allocation factors. It does not compare those five-minute prices directly to
the half-hourly, time-weighted publication CSV; publication aggregation and
rounding remain a separate canonical parity surface. The validator indexes
period, node, bus, island, and transfer relationships once so daily validation
is linear in the evidence size. With the observed single-node network
entitlement, this command must wait while historical population enumeration
owns the GAMS session.

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

Apply the separately named compact semantic policy with:

```bash
uv run python -m tools.gate12.validate_semantic_replay \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --trading-date 20221106 \
  --output /path/to/incremental/semantic-results/20221106.json
```

The command exits nonzero while any material path remains unresolved. Its
immutable output binds both bundle hashes, the complete hexadecimal tolerance
policy, accepted-reason counts, unresolved-reason counts, and bounded path
examples. It does not delete or reinterpret the exact diff. Report-schema
differences stay fail-closed as `report-crosswalk-required`; raw `+/-500000`
sentinels are accepted only when the corresponding repaired-bus values match
within the price tolerance.

Generate the independent report-schema crosswalk with:

```bash
uv run python -m tools.gate12.crosswalk_report_schemas \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --trading-date 20221106 \
  --output /path/to/incremental/report-crosswalks/20221106.json
```

The crosswalk loads and hash-verifies both complete bundles, requires matching
source/work-item/case provenance, recognizes only the 13 declared Authority
table suffixes, rejects duplicate or malformed schemas, and records every
mapped and unsupported field. Direct mappings, wide-to-long pivots, and
derived fields are named separately. Its scope is deliberately
`schema-only-no-row-value-parity-claim`: it exits nonzero for unsupported
Authority fields, unmatched candidate fields, or candidate-only tables. A
later row projector must use only proven mappings and retain identity, unit,
precision, cardinality, and value differences before `report-field` can pass.

Project the proven mappings onto identity-strict rows with:

```bash
uv run python -m tools.gate12.project_report_rows \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --schema-crosswalk /path/to/incremental/report-crosswalks/20221106.json \
  --trading-date 20221106 \
  --output /path/to/incremental/report-row-parity/20221106.json
```

The runner re-hashes the crosswalk, verifies that every embedded case mapping
exactly recomputes from the paired report surfaces, and compares numeric values
against half of the Authority field's displayed unit. It never treats a
missing zero row as present. The current first-date artifact compares 13,133
mapped values with zero missing or extra identities. All 4,368 branch flows,
252 branch-constraint values, 96 market-node-constraint values, 395 offer
quantities, and all reserve price surfaces pass. Only four values exceed
Authority display precision, all in case `61012022110425024`: bus 816, bus 820,
node `WPT1101`, and its `TP35` rolling publication. Risk and summary remain
unimplemented row projections in each case. The compact evidence index is
[`report-row-parity-20221106.json`](report-row-parity-20221106.json).

The bus 816/820 and `WPT1101` differences in that immutable artifact were
opposite subgradient choices at passive, zero-flow AC-loss leaf buses. The
historical GAMS rerun selected the load endpoint for the target case and
remains immutable evidence of the non-unique dual face.

The refreshed run also established that pinned GAMS does not select the same
side of every zero-flow loss kink. Its source-topology certificate remains a
valid classification of that historical run. Following the decision that the
supplied CPLEX corpus is the gold standard, qualified PySPD pricing now selects
the CPLEX-compatible export endpoint. A 2023-08-02 six-case rerun reduces the
worst WPT1101 published difference from `0.49680` to `8.30e-6 NZD/MWh`; see
[`wpt1101-cplex-parity-20230802.md`](wpt1101-cplex-parity-20230802.md). See also
[`wpt1101-zero-flow-price.md`](wpt1101-zero-flow-price.md) and the hash-bound
[`post-WPT rerun certificate`](post-wpt-rerun-certification-20221106.md).

The branch identity failures exposed a candidate reporting omission. Two of
the missing rows per case are nonzero HVDC links (`BEN_HAY1.1` and
`BEN_HAY2.1`); the report renderer exported `branch_flow` but not the separately
registered `hvdc_flow`. The other missing rows are open/inactive branches that
Authority retains with zero flow while preprocessing correctly excludes them
from the optimization domain. The normalized network now carries a separate
full report-only branch domain; the renderer emits AC and HVDC solved values
and explicit zeros only for report-domain identities absent from both solved
components. Probity tests cover both paths. The replacement replay proves zero
missing branch identities. Dead-node bus reporting now also follows pinned
vSPD by transferring the dead node's price through its allocation factor; this
removed all eight false zero-price differences without rewriting old bundles.
`SystemOFV` is intentionally unsupported: pinned vSPD adds
its scarcity-limit-by-price constant to the summary value even though that
constant is omitted from the solved objective, and the current PySPD summary
has no equivalent derived field.

The expanded `authority-pyspd-mapped-report-row-parity-v2` projector also
reconstructs branch and market-node constraint RHS/sense from Pyomo lower and
upper bounds. All 348 constraint observables now have exact identity coverage
and pass at Authority display precision. Report extraction explicitly prefers
`pricing_model` and falls back to `primary_model` only for profiles without a
separate pricing model. The old v1 evidence remains unchanged.

After recreating the independently loaded source-matrix certificate for the
exact replacement bundle, pass it to `project_report_rows` with
`--bus-price-certificate`. The runner verifies the date, source hash, reference
and candidate bundle hashes, complete case order, and passing certificate
disposition before selecting
`authority-pyspd-mapped-report-row-parity-bus-certified-v2`. Only repaired-bus
price value differences are classified by this route; identities, branch and
constraint physics, publications, unsupported fields, and unimplemented tables
remain fail-closed.

Create case-specific bus-dual evidence from the independently loaded GDX
allocation matrix with:

```bash
uv run --group gdx python -m tools.gate12.certify_bus_price_degeneracy \
  --input /path/to/Pricing_20221106.gdx \
  --system-directory /path/to/gams-system-directory \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --trading-date 20221106 \
  --output /path/to/incremental/bus-price-certificates/20221106.json
```

Pass the resulting immutable artifact back to `validate_semantic_replay` with
`--bus-price-certificate`. The validator verifies the date, source hash, both
bundle hashes, case order, allocation hashes, and passing disposition before
selecting the distinct
`gams-pyspd-semantic-tolerance-bus-certified-v1` profile. Only numeric raw and
repaired bus differences are resolved by this certificate; report structure,
publication, or any missing price identity remains fail-closed.

Investigate an above-tolerance rounded publication value with a bounded
qualified alternative run using:

```bash
uv run --group gdx python -m tools.gate12.certify_published_price_degeneracy \
  --input /path/to/Pricing_20221106.gdx \
  --system-directory /path/to/gams-system-directory \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --trading-date 20221106 \
  --run-root /path/to/incremental/published-price-runs \
  --output /path/to/incremental/published-price-certificates/20221106.json
```

The runner discovers the discrepant period, selects its immediate warmup and
all period cases from the GDX order, requires every target case to complete and
requires zero predecessor-generation fallback. It binds the alternative report
manifest and execution source. The first formal pre-correction 2022-11-06
attempt correctly failed: its optimal no-fallback result was `13.18042
NZD/MWh`, `0.00161` from
the GAMS `13.18203`. A prior diagnostic optimal run produced `13.18202`, but
the favorable observation is not selected after the fact as passing evidence.
On that pre-correction bundle the governed result is `13.18148`; its separately
bound alternative returned `13.17947`, so the validator again fails. The
variable outcomes establish a solver-sensitive surface; a reproducible bounded
envelope or stronger common-optimal-face certificate is still needed. In the
refreshed post-WPT prefix, the governed WPT1101 publication is `13.18718`
versus GAMS `13.18203`. The new source-topology certificate reconstructs
`13.18718` exactly from the six weighted cases, superseding the alternative-run
diagnostic for this convention-bound surface.

Create that immutable zero-flow convention certificate directly from the
official input GDX, the pinned GAMS result GDX, and the two canonical bundles
with:

```bash
uv run --group gdx python -m tools.gate12.certify_zero_flow_price_convention \
  --input /path/to/Pricing_20221106.gdx \
  --reference-result-gdx /path/to/pyspd_gate12_results.gdx \
  --system-directory /path/to/gams-system-directory \
  --reference-bundle-root /path/to/incremental/gams-bundles \
  --candidate-bundle-root /path/to/incremental/pyspd-bundles \
  --trading-date 20221106 \
  --output /path/to/zero-flow-price-certificate.json
```

Pass the resulting artifact to both `validate_semantic_replay` and
`project_report_rows` with `--zero-flow-price-certificate`. Each consumer
revalidates the certificate hash, source and bundle provenance, complete case
order, and passing disposition before accepting only exact certified bus,
node, and publication identities. All unrelated values remain fail-closed.

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
