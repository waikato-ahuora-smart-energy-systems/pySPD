# ADR-0029: Execute independent trading periods through bounded worker processes

| Field | Decision |
|---|---|
| Status | Accepted for the SCIP/HiGHS application profile |
| Date | 2026-09-05 |
| Decider | Project owner direction to continue the ten-worker implementation |

## Context

The governed benchmark runner already assigned trading-period jobs dynamically,
but the stable `pyspd run` entry point remained serial. Directly sending a
prepared Pyomo case through `multiprocessing` is unsafe: immutable runtime
mappings are not pickleable and each accepted solve retains live Pyomo and
solver objects. The former planner also fully preprocessed every period merely
to discover whether it had an explicit generation start, adding 126–130
seconds before workers could start on a complete day.

## Decision

`ApplicationConfiguration.worker_count` is explicit, positive, included in the
configuration hash, and defaults to one. `pyspd run --workers N` provides a
hash-bound override. Counts greater than one use bounded spawn-based worker
processes with one case per dynamically assigned job.

The parent reads only the immutable source inventory and classifies each
generation-start boundary directly from `initialMW`, `solvedInitialMW`, study
mode, and primary/secondary-offer mappings. A job may start only where this
classifier proves predecessor independence. Each worker caches one validated
GDX/index view, solves and renders complete case reports locally, then returns:

- a portable result with the live solver payload deliberately removed; and
- complete report rows produced while the solver model is still available.

The parent restores canonical ordinal and event order, aggregates published
prices, merges report rows, and writes the ordinary report bundle and manifest.
Repeated labels remain distinct through full period identity.

All unordered reserve-domain inputs are sorted before constructing Pyomo
components. This prevents process-specific Python hash seeds from changing
constraint identities or matrix order.

## Consequences

The public output directory and report schema are unchanged. Parallel
`ApplicationRun` results preserve all public numeric mappings and prices, but
their accepted observations intentionally have `solve_payload=None`; live
solver models do not cross the process boundary. Report completeness is not
affected because each worker renders before stripping that payload.

On the two-period 2019-02-18 trial, two workers reduced wall time from 56.27 to
36.87 seconds (34.48%). All 70,470 report-row identities and their order
matched. Every value was exact except eight island aggregates, whose maximum
difference was `5e-14` MW. Published prices were byte-identical.

The 322-case 2022-11-01 source boundary now takes 12.41 seconds: 12.34 seconds
to load, validate, and index the GDX and 0.073 seconds to classify starts. This
replaces the measured 126–130 second full-preprocessing planning pass.

The subsequent full 2019-02-18 execution completed all 48 periods through the
actual `--workers 10` CLI override in 399.66 seconds. Its round-trip-validated
manifest contains 12 tables and 1,654,840 rows, including 25,536 published-price
rows. This also makes the next bottleneck explicit: 1,504,321 constraint rows
account for about 208 MiB of the 224 MiB report directory.

## Rejected alternatives

- A combined multi-period Pyomo model remains rejected for the separable vSPD
  profile because the qualified trial was slower and greatly increased matrix
  size.
- Pickling live Pyomo models was rejected because the runtime graph and mapping
  proxies are not a stable process contract.
- Threads were rejected because solver bindings and model state need process
  isolation.
- Treating every period as independent without inspecting generation starts was
  rejected because it could silently bypass predecessor initialization.

## Verification

Probity tests cover worker-count validation and hashing, CLI override behavior,
portable result round-tripping, canonical event reconstruction, full-period
identity, generation-start semantics, bounded scheduling, and worker failure
attribution. The real serial/parallel report comparison is recorded in
`docs/gate-12/parallel-application-integration-20190218.json`.

## Revisit triggers

Revisit if inter-period ramping or storage makes periods genuinely coupled, if
the solver exposes a qualified native batch interface, or if a corpus case
cannot be partitioned at a proven generation-start boundary.
