# Gate 11 compatibility matrix

| Dimension | `vspd-v5.0.6-reserve` | `spd-v16.0-reserve` |
|---|---|---|
| Selection | Explicit formulation ID | Explicit formulation ID |
| Source baseline | vSPD v5.0.6 commit `21b1cf3…` | SPD v16 PDF plus EA feature commit `84ed3c9…` |
| Effective-date rule | Existing versioned v5 source rules | Fail closed before 23 June 2026 |
| Schema | Pinned v5 catalog | 44 symbols, including required `i_busUnitAndKey3Match` |
| Preprocessing | v5 preprocessing classes | `Spd16SourcePreprocessor` and `Spd16ModelPreprocessor` replacements |
| Algebra | Qualified v5 component composition | Separate tie-break, battery, reserve-risk, requirement, and economics components |
| Pricing | v5 fixed-discrete policy | Same pathway plus every battery mode fixed; zero-reserve fallback |
| Reports | v5 result schema/renderer | Separate v16 result schema/renderer |
| Bad-price factor | 5 | 3 |
| Qualified local solver path | GAMS/SCIP MIP → fixed-discrete HiGHS RMIP | Same engineering pathway |
| CPLEX | Deferred | Deferred to Gate 12 |
| Platform | macOS arm64 | macOS arm64 |
| Linux x86_64 CI | Skipped by project direction | Skipped by project direction |
| Strict E2E parity | Gate 12 | Gate 12 |

## v16 input-mode boundary

| Mode/input | Gate 11 result | Authorized claim |
|---|---|---|
| RTD July 2026 | schema, preprocessing, assembly, Pyomo solve, oracle solve, canonical matrix validation, and independent node-price validation pass | Representative engineering execution |
| PRSS July 2026 | schema and eight-interval selection characterized | No full-solve/performance claim; Gate 12 |
| NRSS July 2026 | schema characterized; current daily selector has no supported orchestration mode | Unsupported until a separately tested selector profile is added |
| Pre-effective-date RTD | v16 policy rejects | Use the separately selected applicable historical formulation |

The table is fail-closed: an unlisted formulation, missing v16 match symbol,
pre-effective-date v16 source, unsupported run mode, or rejected solve cannot
publish a v16 result.

