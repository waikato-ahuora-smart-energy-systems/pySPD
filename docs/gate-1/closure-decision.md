# Gate 1 closure decision

| Field | Value |
|---|---|
| Gate | G1 — Oracle trusted |
| Decision date | 29 August 2026 |
| Decision | **PASS — CLOSED** |
| Active reference | Optimal SCIP MIP → fixed-discrete HiGHS RMIP under ADR-0008 |
| CPLEX | Deferred cross-validation; not a current blocker |

## Decision

Gate 1 is closed. The executed DPS plus nine-case SPD corpus and one AUD run
prove the active reference profile, fail-closed overlays, standard/audit report
families, canonical GDX/matrix exports, independent LP checks, dead-node price
transfer, and independent node-price mapping across all in-scope 2025-pack
RTD/PRSS inputs. The 2023 pack is hash-bound and validly deferred. The result
is supported by governed preprocessing checkpoints, complete per-invocation
state/matrix dictionaries, and their observational-neutrality proof. The
incremental comparator, complementarity/sign
conventions, basis classification, and controlled performance baseline are also
complete. All 139 corrected daily inputs are individually hash-bound; exact
optimal evidence exercises shortfall transfer, the maximum-loop branch, and
cleanup re-solves; and selected 46- and 50-period daylight-saving fixtures pass.
ADR-0010 therefore satisfies the Gate 1 population criterion at date level and
retains exact identification/replay of all 546 intervals as a mandatory Gate 12
criterion under the amended stage-and-gate plan. Stage 2 production work is
authorized.

## Material blockers

None. `G1-B01` is closed by the accepted qualification policy in ADR-0010 and
its linked date-inventory, affected-path, control-corpus, and daylight-saving
evidence. This closure does not mark the all-546 Gate 12 replay complete.

## Evidence that is complete for the executed samples

- two clean runs with identical logical solve, report, input, solution, matrix,
  and dictionary hashes;
- three governed preprocessing checkpoints and complete pre/post state pairs for
  every operational solve, with raw and canonical hashes;
- a semantic GAMS Convert matrix and scalar/name dictionary bound to every
  operational solve ordinal, model variant, solve type, scenario, and solver;
- a checkpoint-disabled control run with exact logical equality across solve
  records, all reports, published prices, pricing solution, matrix, dictionary,
  independent validation, and configuration;
- 38 optimal SCIP primary MIPs and 38 optimal HiGHS fixed-discrete RMIPs in the
  frozen RTD/PRSS/AUD corpus;
- ten deterministic GAMS Convert matrix/name-dictionary exports;
- independent activity, row/column bound, raw/scale-normalized stationarity,
  dual-side sign, and complementarity validation;
- exact semantic DictMap coverage plus a versioned cumulative Stage 4--7
  projection/sign/split/auxiliary contract with analytic tests;
- a classified primal-simplex/no-presolve basis perturbation with identical
  structure and objective but alternative optimal primals/duals;
- controlled phase, per-solve, wall-time, and peak-RSS reference measurements;
- exact native node-price reconstruction for the nine nodes in the final
  DPS scenario snapshot, with report-precision agreement;
- hash-bound, fail-closed SPD and AUD configuration overlays;
- 13 normal reports and the AUD family of six CSVs plus `AllData.gdx`; and
- exact native reconstruction of all 20,344 frozen-corpus prices, including 38
  dead-node price transfers, with five-decimal report-precision agreement;
- exact recovery/classification hashes for the named 2023 and 2025 Authority
  packs; and
- keyed official comparisons for every in-scope 2025-pack RTD/PRSS case, with
  CPLEX differences retained as secondary solver-profile divergences;
- all 139 corrected daily GDX inputs individually bound by size and SHA-256;
- an exact optimal affected fixture with 10 primary and 7 cleanup SCIP solves,
  21 eligible adjustment records, and material first-loop transfers; and
- exact selected-case runs on 46- and 50-period daylight-saving days, each with
  10 optimal SCIP primary solves and complete standard reports.

## Reconsideration rule

Reopen Gate 1 if immutable evidence cannot be regenerated, a retained input
changes identity, or Gate 12 replay discovers an oracle/comparator inconsistency
that invalidates this decision. ADR-0009 confirms that independent review is
not required. CPLEX evidence is required only if the proposed claim is expanded
to CPLEX-specific parity.
