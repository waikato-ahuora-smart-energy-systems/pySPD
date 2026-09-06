# Gate 7 checklist

| Criterion | Evidence | Result |
|---|---|---|
| All in-scope variables/equations traced | `source-map.md` | PASS |
| FIR/SIR and PLRO/TWRO/ILRO | analytic tests plus exact matrix | PASS |
| All eight risk classes | per-class binding/nonbinding tests; secondary-enabled build | PASS |
| Generator/group/manual/DC/link/secondary algebra | source map, matrix, independent validator | PASS |
| Reserve cover and scarcity | 1,211 independent residuals | PASS |
| Bidirectional NMIR sharing and zones | portable full solve and identity recomputation | PASS |
| Matrix/objective parity | 15,381 columns and 1,403 rows; identical hashes | PASS |
| SCIP-MIP → fix all discrete → HiGHS-RMIP | 124/124 fixed, zero pricing discrete/SOS | PASS |
| Energy price | rebuilt load perturbation error `1.61e-4` | PASS |
| Reserve price | fixed-RMIP RHS perturbation error `3.01e-6` | PASS |
| Primary/pricing snapshot isolation | distinct state hashes, identical algebra hash | PASS |
| Independent physical/economic checks | max residual `8.94e-8` at `1e-6` tolerance | PASS |
| Exact perturbation constants | `0.0005`, `1e-5`, `2e-5`, `3e-5` | PASS |
| Affected Gate 6 behavior rerun | full repository suite, 213 passed/1 skipped | PASS |
| Probity TDD | behavioral red, 16-test green, committed blob hashes | PASS |
| Ruff and mypy | clean | PASS |
| CPLEX | deferred by ADR-0008 | NOT CLAIMED |
| Linux x86_64 | deferred by ADR-0011 | NOT CLAIMED |

No unexplained material formulation mismatch or in-scope blocker remains.
