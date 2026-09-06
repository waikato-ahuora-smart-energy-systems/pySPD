# Indexed network model-build optimization — 2022-11-06

Profiling showed that each bus equation repeatedly scanned every AC branch,
offer, bid, node allocation, and loss segment. In the HVDC formulation, the
base AC energy-balance component was also fully constructed and then deleted
and reconstructed with HVDC terms.

`NetworkBuildIndex` now creates deterministic incidence lists once per model.
The class-based AC component builds its energy balance through an overridable
method, so `HVDCACNetworkComponent` directly constructs the required equation
without creating the discarded AC-only version.

The first four consecutive cases from the hash-pinned `Pricing_20221106.gdx`
were run twice through the cold SCIP-MIP → fixed-state HiGHS-RMIP path.

| Metric | Previous | Indexed build | Change |
|---|---:|---:|---:|
| Median four-case solve wall time | 82.217 s | 55.959 s | 31.94% faster |
| Preparation plus solve | 94.832 s | 68.514 s | 27.75% faster |
| Versus original pre-GDX baseline | 127.287 s | 68.514 s | 46.17% faster |

All primary and pricing solves reported optimal. Both candidate repetitions
produced the same result hash. The candidate primary model retained 57,073
variables and 32,370 rows. Its nine-decimal normalized canonical matrix hash
exactly matched the pre-refactor model (`b263d8dc…`), covering bounds,
domains, objective coefficients, row bounds, identities, and coefficients.
The unrounded hash changes because the old code accumulated terms in randomized
`frozenset` order; the normalized equality confirms algebraic equivalence.

Decision: accept and enable deterministic indexed model construction. Do not
introduce persistent solver state yet: structural variation and fixed-RMIP
state invalidation still require an independent design and benchmark.

The machine-readable record is
[`model-build-trial-20221106.json`](model-build-trial-20221106.json).
