# Solve-performance investigation — 2023-09-27

## Decision

Use independent case processes as the primary acceleration mechanism, with one
SCIP thread and one HiGHS thread per worker. Use ten workers for complete-day
throughput on this Darwin arm64 host when memory capacity permits; retain three
workers as the lower-memory setting and for small workloads. Keep
period-to-period SCIP initialization and HiGHS primal warm starts disabled.
Enable the indexed case-data extractor and clone the solved primary Pyomo model
when constructing the fixed-discrete pricing RMIP.

The qualified solver path remains SCIP MIP → fix all discrete/SOS state →
HiGHS RMIP. The earlier full-day CLP experiment was 7.60% faster than HiGHS but
selected different valid duals on degenerate faces; it remains an experimental
validation path rather than the CPLEX-qualified default.

Machine-readable evidence is in
[`solve-performance-investigation-20230927.json`](solve-performance-investigation-20230927.json).

## Controlled workload and correctness contract

The controlled trials use the first 12 ordered cases from hash-pinned
`Pricing_20230927.gdx` (`c854ea9e…`). Every selected case has a nonzero source
generation start, so the six-case and four-case shard boundaries do not invoke
the daily predecessor-generation fallback. Parallel output is merged in source
order and compared with the serial JSONL record stream.

The later infrastructure trial uses all 263 ordered cases from the same source.
Every case has an explicit generation start, so all 3-worker and 10-worker
boundaries are independently valid. Its raw comparison remains strict and its
market acceptance additionally applies the established analytical-price-
interval rule.

Every accepted timing requires:

- optimal SCIP primary and HiGHS pricing solves;
- independent reserve validation;
- identical identities, solve counts, and fixed-discrete state;
- physics, pricing objective, raw-bus price, and market-price parity; and
- comparison of all 46,464 result values.

The maximum primary-objective difference across process boundaries was below
`6e-9 NZD`; physics, pricing objectives, raw prices, and market prices were
exact. This is stricter than the governed CPLEX-compatible market-result
boundary.

## Runtime decomposition

An eight-case profile before pricing-model cloning took 134.019 seconds end to
end and peaked at 4.175 GB resident memory.

| Phase | Seconds | End-to-end share |
|---|---:|---:|
| SCIP primary MIP | 47.345 | 35.33% |
| HiGHS pricing and sensitivity LPs | 32.641 | 24.36% |
| Two Pyomo model assemblies | 19.173 | 14.31% |
| Result extraction and price logic | 20.603 | 15.37% |
| GDX load, catalog validation, and case preparation | 14.110 | 10.53% |
| Daily runner overhead | 0.147 | 0.11% |

Some cases need additional support-polishing or price-interval sensitivity
solves. Those calls explain the case-to-case imbalance and are part of the
CPLEX evidence boundary; they must not be removed merely to improve timing.

## Implemented improvements

### Indexed case extraction

The former application path rescanned all 3,527,523 case-scoped source records
for every selected case. `DailyCaseDataIndex` now scans them once, records all
source-order ranges for each requested case, and retrieves only those slices.
It handles noncontiguous records and fails closed when asked for a case outside
its declared scope.

Across 24 cases and three alternating repetitions, extraction fell from a
1.465-second median to 0.108 seconds: 13.52× faster, or 92.60% less elapsed
time. All 357,798 extracted records and complete `CaseData` values matched the
legacy scan exactly. This is a useful low-risk improvement, although extraction
is a small fraction of a complete solve.

### Clone the pricing model

The fixed RMIP has the same algebra and artifact graph as the solved primary
model. `ModelAssembler.clone()` now clones that exact model, remaps every owned
Pyomo component—including components nested in tuples—and shares only immutable
data artifacts. Missing clone artifacts fail closed. The pricing path then
applies the unchanged discrete/SOS fixing and relaxation overlay to the clone,
leaving the primary model intact for audit.

An isolated representative model clone took 0.476 seconds versus 1.096 seconds
for a second assembly, a 56.60% reduction. On the full 12-case governed path,
solve time fell 7.28% (184.591 to 171.159 seconds) and wall time fell 5.48%
(223.483 to 211.241 seconds). All 46,464 compared values passed strict parity.

### Multiprocessing infrastructure

`ContiguousCaseShardPlanner`, `DynamicCaseJobPlanner`, and
`ProcessShardCoordinator` now provide the retained class-based execution path.
The static planner creates deterministic balanced half-open ranges. The dynamic
planner creates small canonical jobs and the coordinator keeps at most one job
per worker in flight, assigning the next job whenever a worker becomes idle.
Both planners cap excess workers at the job count and fail closed when an
internal job would start at a case that needs predecessor-generation fallback.
The coordinator uses the portable `spawn` process context, returns artifacts in
source order even when jobs finish out of order, cancels pending work after a
failure, and identifies the exact failed job and first case.

`tools/run_parallel_solver_path.py` applies that infrastructure to the governed
solver benchmark. It refuses to overwrite an existing evidence target, runs
each shard in an isolated solver process, bounds each worker's case-data index
to its declared range, retains a per-shard log and benchmark, merges all JSONL
records in canonical order, and records preparation, execution, merge, and
total timing separately. A real two-worker, three-case process smoke test
completed optimally and independently validated before the full-day trials.

## Parallel processing

The serial and parallel trials used identical case groups and one thread inside
each solver.

| Workers | Wall time | Speedup | Wall reduction | Result |
|---:|---:|---:|---:|---|
| 1 | 223.483 s | 1.00× | — | optimal, validated |
| 2 | 122.875 s | 1.82× | 45.02% | strict parity |
| 3 | 88.595 s | 2.52× | 60.36% | strict parity |
| 10 | 94.000 s | 2.38× | 57.94% | strict parity |

A repeat after pricing-model cloning took 93.508 seconds, or 55.73% less than
the cloned serial path. The repeat was slower than the first three-worker run
because the middle shard's solver time increased; the results therefore
support a measured three-worker reduction range of 55.7–60.4%, not an additive
parallel-plus-clone claim.

A subsequent ten-worker trial split the same 12 cases into two two-case shards
and eight one-case shards. It completed in 94 seconds overall (93.325 seconds
for the slowest shard), with every solve optimal and independently validated.
All 46,464 values retained strict parity; the maximum primary-objective
difference was `4.89e-9 NZD`, while physics, pricing objectives, raw prices,
market prices, and fixed-discrete state matched exactly. Ten workers were 0.53%
slower than the 93.508-second three-worker repeat and 6.10% slower than the
best three-worker run. Their summed solver time rose from 183.014 to 287.778
seconds, a 57.24% increase, demonstrating CPU and memory-bandwidth contention
rather than useful additional scaling. Ten workers are therefore valid but not
recommended on this host.

That small-workload conclusion does not generalize to a complete day. A
subsequent matched 263-case run through the retained coordinator produced:

| Workers | Preparation | Worker execution | Merge | End to end | Cases/min during execution |
|---:|---:|---:|---:|---:|---:|
| 3 | 126.310 s | 1,431.184 s | 3.357 s | 1,561.450 s | 11.03 |
| 10 | 129.702 s | 601.775 s | 3.384 s | 735.470 s | 26.22 |

For the full day, ten workers were 2.378× faster during worker execution and
2.123× faster end to end: reductions of 57.95% and 52.90%, respectively.
Summed solver time increased from 3,451.392 to 4,184.930 seconds (21.25%), so
the additional processes still incur contention, but the shorter shards more
than compensate at this workload size. The ten-worker slowest shard took
600.122 seconds and the fastest 513.536 seconds; the three-worker range was
1,328.487–1,429.698 seconds.

Both runs completed all 263 cases optimally and passed independent validation.
The ten-worker result was compared with the three-worker result across
1,013,096 internal values. Physics matched to `3.41e-12`, the maximum primary
objective difference was `1.49e-5 NZD`, and the maximum pricing-objective
difference was `4.66e-10 NZD`. One degenerate reserve-sharing choice selected
the opposite pair of zone binaries in case `261302023091200863` without
changing physics or prices.

Raw strict parity also identifies case `261012023091940036`: its three affected
node prices selected opposite endpoints of the same independently calculated
interval. At the published TP18 boundary, only 3 of 25,584 price rows differ,
by `0.03105 NZD/MWh`; both values are the endpoints of the identical
`[149.90607, 149.93712]` interval. Under the established Gate 12 rule that any
value inside the analytical interval is accepted, complete-day market results
therefore pass the interval-aware evidence boundary. The raw strict comparator
correctly remains false because it intentionally requires identical binary
choices and scalar dual endpoints.

The already retained full-day evidence is consistent with this result:

- 2023-09-26: 295 optimal and independently validated cases in 1,774.3 seconds
  maximum worker wall time; and
- 2023-09-27: 263 optimal and independently validated cases in 1,486.6 seconds
  maximum worker wall time.

The corresponding sums of individual shard wall times are 5,245.3 and 4,339.1
seconds, yielding observed concurrency factors of 2.96× and 2.92×. These are
throughput observations, not matched serial-day speedups.

Parallel execution has two hard safety constraints:

1. A shard may start independently only when its first case has an explicit
   source generation start. If it would use the predecessor-generation
   fallback, the dependency chain must remain in one shard or receive a
   validated predecessor checkpoint.
2. A single eight-case process peaked at 4.175 GB. Three workers therefore need
   roughly 12.5 GB for worker peaks, plus operating-system and merge headroom.
   Ten workers completed successfully on this host, but their aggregate peak
   memory was not instrumented; deployment must retain explicit memory
   headroom and fall back to a smaller worker count where necessary.

Dynamic small-job scheduling now addresses solve-time imbalance while retaining
the generation-start, memory, source-order, and fail-closed contracts. Job size
remains configurable because one-case jobs improve balancing while multi-case
jobs amortize repeated GDX preparation.

## Initialization and persistence

The 12-case SCIP initialization trial ran cold and warm modes twice in reversed
order. Each successor received 12 prior-period discrete values. Cold median
time was 193.343 seconds; initialized median time was 193.721 seconds, a 0.195%
slowdown. Results and published output were byte-identical across 46,464
values. The earlier four-case 2022 trial was also 0.469% slower. SCIP warm
starting remains a correct opt-in diagnostic but is not a speed feature.

HiGHS primal initialization remains rejected: the earlier controlled smoke
trial was 7.01% slower and changed a degenerate raw-dual basis. The fixed-RMIP
must remain independently solved for qualified prices.

Constructing the Pyomo HiGHS interface was measured 100 times. Its median cost
was 38 microseconds and all 100 constructions took 0.0041 seconds. Caching that
factory object cannot materially improve runtime. A genuine persistent-solver
gain would require reusing and safely updating the same Pyomo model and native
matrix across periods. Because topology, domains, SOS sets, fixings, and price
sensitivity overlays vary, that is a separate high-risk design, not a backend
object cache.

## Remaining opportunities

The first two former priorities are now complete. ADR-0029 integrates bounded
dynamic processes into `pyspd run`, and replaces the complete-day preparation
pass with direct generation-start classification. On 2022-11-01 the new parent
planning path took 12.41 seconds for 322 cases, including only 0.073 seconds for
boundary classification, rather than the prior 126–130 seconds. A real
two-period report run was 34.48% faster with two workers and retained all
70,470 identities in canonical order.

A complete 48-period 2019-02-18 production run through `pyspd run --workers
10` finished in 399.66 seconds. Its manifest round trip verifies 1,654,840
rows. The constraint table alone contains 1,504,321 rows and occupies about
208 MiB, confirming report-surface selection and extraction as the next
performance target.

The next performance work, in priority order, is:

1. profile and index the result/report builders—one diagnostic case spent about
   1.95 seconds constructing reports, including 1.08 seconds in model-row
   extraction;
2. investigate within-case reuse for reserve price-sensitivity LPs, retaining
   every analytical interval and CPLEX parity test; and
3. consider a parameterized model template/persistent matrix only after a
   corpus-wide structural-signature study proves which periods are safely
   reusable.

Increasing SCIP or HiGHS threads inside each case is lower priority. The MIP
surface is small, HiGHS simplex is not usefully parallel at this scale, and
case-level processes already provide strong scaling while preserving the
single-thread deterministic solver contract.

## Probity TDD and repository verification

The case-index test was first observed red as an import failure for the missing
`DailyCaseDataIndex`. The clone-boundary test was first observed red with
`AttributeError: ModelAssembler has no attribute clone`, then again proved that
the solve policy had not yet invoked the clone. Implementation followed those
red observations. The green tests cover noncontiguous source records, declared
index scope, cloned component and tuple-artifact ownership, primary/clone state
independence, and use of the clone specifically for the pricing model.

The multiprocessing additions were developed from observed red tests for the
missing API and nonpositive preparation bound. The tests cover balanced and
capped plans, canonical inventory checks, predecessor-dependent rejection,
bounded in-flight dynamic assignment, ordered collection, and failed-job
identification.

Final verification on the implemented source is:

- `uv run pytest -q`: 648 passed, 3 skipped;
- `uv run ruff check .`: passed; and
- `uv run mypy src tools`: passed across 145 source files.
