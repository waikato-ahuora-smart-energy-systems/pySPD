# Solve-performance investigation — 2023-09-27

## Decision

Use independent case processes as the primary acceleration mechanism, with one
SCIP thread and one HiGHS thread per worker. Three workers are the measured
default for this Darwin arm64 host when at least 13 GB is available to the
workers. Keep period-to-period SCIP initialization and HiGHS primal warm starts
disabled. Enable the indexed case-data extractor and clone the solved primary
Pyomo model when constructing the fixed-discrete pricing RMIP.

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

## Parallel processing

The serial and parallel trials used identical case groups and one thread inside
each solver.

| Workers | Wall time | Speedup | Wall reduction | Result |
|---:|---:|---:|---:|---|
| 1 | 223.483 s | 1.00× | — | optimal, validated |
| 2 | 122.875 s | 1.82× | 45.02% | strict parity |
| 3 | 88.595 s | 2.52× | 60.36% | strict parity |

A repeat after pricing-model cloning took 93.508 seconds, or 55.73% less than
the cloned serial path. The repeat was slower than the first three-worker run
because the middle shard's solver time increased; the results therefore
support a measured three-worker reduction range of 55.7–60.4%, not an additive
parallel-plus-clone claim.

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
   More workers are not recommended without measuring memory and contention on
   the target host.

Contiguous shards preserve source order and minimize orchestration risk, but
support-polishing cases can make them imbalanced. A future scheduler may use
smaller independent chunks only after checking every chunk boundary against
the predecessor-state rule.

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

The next performance work, in priority order, is:

1. add a production-grade process coordinator that performs the generation-
   start boundary check, launches memory-bounded contiguous shards, and merges
   reports deterministically;
2. profile and index the result/report builders—one diagnostic case spent about
   1.95 seconds constructing reports, including 1.08 seconds in model-row
   extraction;
3. investigate within-case reuse for reserve price-sensitivity LPs, retaining
   every analytical interval and CPLEX parity test; and
4. consider a parameterized model template/persistent matrix only after a
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

Final verification on the implemented source is:

- `uv run pytest -q`: 602 passed, 2 skipped;
- `uv run ruff check .`: passed; and
- `uv run mypy src tools`: passed across 141 source files.
