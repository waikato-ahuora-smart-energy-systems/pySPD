# Gate 8 checklist

| Criterion | Evidence | Result |
|---|---|---|
| Same case/period/formulation selection | selector tests and pinned GDX identity | PASS |
| Same representative solve path | SCIP → fixed 124 discrete → HiGHS; event trace | PASS |
| Bounds cannot hang/publish unsolved mutation | explicit final-loop regression | PASS |
| Fallback/degraded states visible | typed status and event tests | PASS |
| Eleven override families and output deltas | override suite and immutable audit | PASS |
| Raw/repaired/published prices traceable | `PriceTrace`, publication tests | PASS |
| Publication weighting and rounding | independent 1,209-check validation | PASS |
| Official prices reported separately | 523/4 identities, full error distribution retained | PASS WITH CLASSIFIED PROFILE DIFFERENCE |
| 546 immutable affected interval identities | 427 recovered; 119 unresolved | **HOLD** |
| All 546 approved assertions replayed | cannot run without complete identities | **HOLD** |
| Representative whole-day economic parity | not executed; per-case solve is about two minutes | **HOLD** |
| Focused tests | 17 passed | PASS |
| Cumulative repository tests | 230 passed, one intentional skip | PASS |
| Ruff and mypy | clean | PASS |
| Probity evidence | behavioral red/green record and repository audit | PASS |
| CPLEX | deferred by ADR-0008 | NOT CLAIMED |
| Linux x86_64 | deferred by ADR-0011 | NOT CLAIMED |

Gate 8 remains held because three mandatory exit assertions are incomplete;
feature completion and passing unit tests do not override the gate criteria.
