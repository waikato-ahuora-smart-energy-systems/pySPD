# GDX preparation optimization — 2022-11-06

The raw GDX adapter now classifies each numeric value column with vectorized
GAMS special-value predicates. The previous implementation invoked five NumPy
predicates separately for each of 2.64 million numeric values. Catalog UEL
membership validation now constructs immutable lookup sets once per symbol
instead of scanning ordered UEL tuples for every record key. Neither change
alters the immutable raw-data contract or case/model code.

The controlled comparison used the first four consecutive cases from the
hash-pinned `Pricing_20221106.gdx`. The baseline was executed from an isolated
archive of commit `c7a04df` with the same Python environment, GAMS 54 runtime,
SCIP, HiGHS, and input file.

| Metric | Baseline | Optimized | Change |
|---|---:|---:|---:|
| Four-case preparation | 45.176 s | 12.615 s | 72.08% faster |
| Four-case solve wall time | 82.111 s | 82.217 s median | 0.13% slower |
| Preparation plus solve | 127.287 s | 94.832 s | 25.50% faster |

The solve-time movement is normal run noise; this change does not alter solver
construction, options, or model formulation. All baseline and candidate SCIP
and HiGHS solves reported optimal.

Semantic validation covered all 3,682,271 source records. Writing the optimized
raw representation through `CanonicalFeed` reproduced the pinned Gate 2 logical
SHA-256 `4ffc656e0ec57f4c77a1e1af9549404d72ef842af04e77ad784ae0ae8f12df9f`
exactly. The full real-GDX integration test also compared every symbol from the
optimized adapter with an independently written and read canonical feed.

Exact result SHA-256 values are not compared across independent solver
processes. The isolated unchanged baseline produced `df64b4c…`, this candidate
produced `dded9cd…` twice, and the prior unchanged trial produced `4bfc69f…`.
That variability exists without the loader change and reflects SCIP selection
on alternate-optimum surfaces. Within each controlled process the result hash
was stable; the governed data boundary is the exact canonical-feed hash, and
Gate 12's tolerance/certificate rules remain the result-validation authority.

Decision: accept and enable the vectorized adapter and set-indexed validation
path. The next performance investigation should profile repeated Pyomo model
construction and evaluate carefully invalidated persistent solver reuse.

The complete machine-readable record is
[`gdx-preparation-trial-20221106.json`](gdx-preparation-trial-20221106.json).
