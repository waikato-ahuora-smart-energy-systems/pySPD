# Full-day solver-path benchmark — 2022-11-06

## Decision

`SCIP MIP -> CLP fixed-RMIP` is the fastest path that completed the full
278-case day with every primary and pricing solve reporting optimal. It used
3,558.088 solver-seconds (59.30 minutes), saving 292.691 seconds (4.88 minutes,
7.60%) against `SCIP MIP -> HiGHS fixed-RMIP`.

The qualified application default remains `SCIP MIP -> HiGHS fixed-RMIP`.
CLP is faster but selected a different valid dual on a degenerate fixed-LP
face at 23:00. Both CBC paths are disqualified because CBC crashed on the same
next MIP case after six successful cases.

## Governed input and runtime

- Input: `Pricing_20221106.gdx`
- Input SHA-256:
  `282ac2abeaa2f0c7c6e26b967e2ba90289c0ba5a9e696b99069d11350d3037b8`
- Expected and reference case count: 278
- Platform: Darwin arm64
- Pyomo 6.10.1; PySCIPOpt 5.7.1; HiGHS 1.15.1; CyLP 0.94.0;
  PuLP 3.3.2
- CBC: PuLP-bundled CBC 2.10.3, 2019 x86_64 binary executed on Apple Silicon
- Validation tolerance: `1e-4`
- Benchmark implementation:
  [`tools/benchmark_solver_paths.py`](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/main/tools/benchmark_solver_paths.py)

The ranked time is measured around the class-based case executor and includes
both the primary MIP and fixed-RMIP solve. GDX loading, model preparation,
independent validation, evidence serialization, and parity aggregation are
excluded. Wall time is also retained. Paths ran serially in the order shown,
with no competing diagnostic workload.

## Results

| Path | Completed cases | Solver result | Solver time | Wall time | Disposition |
|---|---:|---|---:|---:|---|
| SCIP -> HiGHS | 278/278 | all optimal | 3,850.779 s (64.18 min) | 4,018.927 s (66.98 min) | Qualified default/reference |
| SCIP -> CLP | 278/278 | all optimal | **3,558.088 s (59.30 min)** | 3,759.762 s (62.66 min) | Fastest completed optimal; experimental |
| CBC -> HiGHS | 6/278 | CBC exit `-11` after 6 cases | 87.362 s partial | 104.395 s partial | Disqualified |
| CBC -> CLP | 6/278 | CBC exit `-11` after 6 cases | 82.281 s partial | 98.520 s partial | Disqualified |

CBC failed in the primary MIP at case `51012022111130707`, 00:30, before
either fixed-RMIP backend could determine the outcome. The identical failure
proves that switching HiGHS to CLP does not address it. Partial CBC rates are
not extrapolated or compared with the completed-day totals.

## SCIP/CLP result comparison

Across the paired 278 cases:

- fixed-discrete state matched exactly;
- all primary objectives matched exactly because both paths use SCIP;
- maximum fixed-RMIP objective difference was `8.98259e-7 NZD`;
- maximum accepted-physics difference was `1.60345e-8`;
- maximum repaired bus/node price difference was `0.105023544 NZD/MWh`;
- maximum reserve-price difference was `0.000951200 NZD/MWh`; and
- raw bus duals differed by as much as `500000 NZD/MWh` on degenerate
  zero-flow faces, consistent with the already documented raw-dual boundary.

The maximum repaired/node price difference occurs in case
`61012022111000170`, 23:00, at bus `526` / node `ORO1102`: HiGHS returns
`20.417768693 NZD/MWh` and CLP returns `20.522792237 NZD/MWh`. The absolute
difference is `0.105023544 NZD/MWh` (0.514%). The fixed decisions and accepted
physics match and the objective difference remains below `1e-6 NZD`, which is
consistent with dual non-uniqueness. There is no retained pinned-GAMS result
for this tail case in the existing 196-case reference prefix, so this
observation is not promoted to a GAMS parity claim.

## Validation boundary

The independent validator's absolute `pricing_objective_fixed_discrete` check
fails 69 cases in both completed paths. The same cases and nearly identical
residuals occur with both RMIP solvers. The maximum is `0.242064166 NZD` in
case `61012022110800110`, 21:00, where SCIP reports `-5828.198027017 NZD` and
the fixed RMIP returns `-5828.440091183 NZD`; the relative difference is
`0.004153%`. This is retained as the accepted SCIP-MIP optimum/tolerance
boundary established by project direction, not relabelled as an exact
objective match.

One full-day primary incumbent produced a `0.000163712` validator residual at
08:15 in both paths. A diagnostic rerun with the exact predecessor generation
state passed with maximum residual `2.01e-7`, so the excursion was not
reproducible in the fixed-RMIP result. No general tolerance was widened.

Consequently, the benchmark supports two deliberately separate conclusions:

1. fastest complete path whose solvers all report optimal: **SCIP -> CLP**;
2. qualified production/default path with the existing GAMS evidence boundary:
   **SCIP -> HiGHS**.

No path satisfies a new claim of strict, solver-independent raw-dual parity.

## Evidence hashes

| Record stream | SHA-256 |
|---|---|
| SCIP -> HiGHS, 278 cases | `6535b00e4472b0e3736b92cf79c6e02274ed962da30acb32b2a0217a9380adcb` |
| SCIP -> CLP, 278 cases | `1674240f1e33f4ee8338071989b55deb96d241d8a71ffc50245386d8d074be82` |

The executed streaming evidence uses benchmark schema v2. Its compact result
had logical SHA-256
`9867d621dddc61e746cac7800600a966ba6ed0457ec8a54e402bbc3b0e0abc24`.
The CBC streams are partial failure diagnostics and are not qualified as
full-day evidence. The reusable tool is now schema v3: it additionally names
each maximum validator residual and reports the fastest completed-optimal path
separately from strict qualification.
