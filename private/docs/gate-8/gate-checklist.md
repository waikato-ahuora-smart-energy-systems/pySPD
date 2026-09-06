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
| 139 corrected input hashes | complete Gate 1 inventory retained | PASS |
| Current affected-interval boundary | 427 immutable dead-node cases plus exact affected fixture | PASS |
| Exact 546 immutable identities/replay | 119 unresolved; transferred unchanged | GATE 12 |
| Representative whole-day economic parity | transferred unchanged | GATE 12 |
| Strict raw/published price and report parity | transferred unchanged | GATE 12 |
| Focused tests | 17 passed | PASS |
| Cumulative repository tests | 230 passed, one intentional skip | PASS |
| Ruff and mypy | clean | PASS |
| Probity evidence | behavioral red/green record and repository audit | PASS |
| CPLEX | deferred by ADR-0008 | NOT CLAIMED |
| Linux x86_64 | deferred by ADR-0011 | NOT CLAIMED |

Gate 8 is closed for the amended evidence boundary approved by the project
owner. Items marked `GATE 12` remain mandatory before an E2E parity claim and
have not been counted as passing evidence here.
