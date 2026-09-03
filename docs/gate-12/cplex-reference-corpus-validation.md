# CPLEX reference corpus and solver-path validation

| Field | Value |
|---|---|
| Evidence date | 2026-09-04 |
| Environment | macOS arm64 |
| CPLEX authority | User-supplied vSPD solved-result archive |
| Candidate pathways | SCIP MIP → HiGHS fixed-RMIP; SCIP MIP → CLP fixed-RMIP |
| Package execution | `uv run` |
| Exact CPLEX parity decision | **NOT ESTABLISHED for either pathway** |
| Operational default | **SCIP MIP → HiGHS fixed-RMIP** for overall CPLEX-field fidelity |

## Decision

Both pathways produced complete, optimal result sets for the designated 2019
and 2023 days. They are physically consistent with one another, and neither
lost a case. Neither pathway reproduces every CPLEX value at the authority
files' displayed precision. Solver-dependent duals, reserve allocation and
risk-setter selection remain observable. The original 2023 WPT1101
published-energy difference of 0.49680 NZD/MWh has since been eliminated by
the CPLEX-compatible zero-flow endpoint described below.

SCIP → HiGHS is retained as the default correctness pathway because it has
fewer total above-precision CPLEX fields and substantially fewer offer and
constraint-dual differences. SCIP → CLP is a valid complete optimal pathway
and is faster, but it is not a drop-in exact-parity replacement. CLP is closer
on the count of published-energy prices and on the worst 2023 summary-cost
difference, so the evidence does not support claiming that either backend
dominates on every output surface.

## Immutable ten-day corpus

The repository-local corpus is in
[`tests/fixtures/cplex_reference`](../../tests/fixtures/cplex_reference). Its
selection algorithm, byte counts and SHA-256 hashes are bound by
[`manifest.json`](../../tests/fixtures/cplex_reference/manifest.json) and
verified by `tests/data/test_cplex_reference_corpus.py`.

| Year | Selected dates | Execution date | Schema |
|---|---|---|---|
| 2019 | 2019-02-18, 2019-05-16, 2019-06-05, 2019-06-06, 2019-06-22 | 2019-06-22 | `vspd-v3-final-pricing` |
| 2023 | 2023-01-26, 2023-02-14, 2023-08-02, 2023-09-22, 2023-11-24 | 2023-08-02 | `vspd-v5.0.6` |

The deterministic random sample contains 145 authority files: ten input GDX
files and 135 result CSV files. Their combined size is 680,928,800 bytes
(649.38 MiB). Every one of the 1,731 sampled CPLEX summary rows reports solve
status 1. The fourth- and fifth-ranked dates in each year were subsequently
replayed through SCIP → HiGHS; see
[`cplex-reference-expanded-four-days.md`](cplex-reference-expanded-four-days.md).

## Validation boundary

The comparison covers every CPLEX row and field for which the governed PySPD
report crosswalk has an implementation. For 2023 this includes all raw
case-level result tables, base offer/reserve results, the arithmetic-average
base-node output, and publication-duration-weighted energy and reserve prices.
For 2019 it includes the case-level mapped tables and base node/offer/reserve
results. The legacy daily `SystemResults`, `TraderResults`, empty scarcity
file, and legacy summary columns for unsupported constraint families are
retained in the corpus but are not represented as exact PySPD report surfaces.
Accordingly, “complete” below means every selected case and every implemented
mapped surface; it is not a claim that those legacy aggregate schemas have
been recreated.

The comparator is identity-strict and fail-closed. Differences are accepted as
certified only where the existing governed row validator proves the declared
alternative-allocation convention. It does not rewrite CPLEX values. Full
JSONL records are regenerable and excluded from Git because they exceed normal
repository-hosting limits; the compact summaries bind them by SHA-256.

## Corrections found by the corpus

The exercise found and tested these defects before the final runs:

1. The legacy v3 final-pricing input required an explicit class-based
   `LegacyV3InputAdapter`, 48-case mode-111 selection, and ramp-unit conversion
   from MW/minute to MW/hour.
2. PRSS mode 130 was incorrectly excluded from source generation ramp limits.
   `CoreDomainsComponent.RampOffer` now applies those limits to every positive
   primary offer, matching vSPD. The explicitly governed v5 structural
   fingerprint consequently changed from `592a9729…7801` to
   `414d7c57…6ff8`; the non-regression test was updated only after the CPLEX
   result established the missing constraint domain.
3. Island load reporting had reused bus rows, which can count a cleared bid at
   multiple mapped buses. It now implements vSPD's allocated fixed node load
   plus cleared island bid exactly once.
4. A CLP value of −2.98×10⁻¹¹ MW on a physically zero HVDC flow selected the
   reverse-capacity report branch. A tested 1×10⁻⁹ MW report-direction zero
   convention now reports the correct 780 MW forward capacity while preserving
   the raw flow value.
5. Long legacy models needed stable SCIP settings: dual simplex for initial and
   resolve LPs, 1×10⁻⁶ feasibility tolerance, and symmetry handling disabled.
6. Report constraint-dual lookup was indexed rather than repeatedly scanned;
   report projection fell from about 40 seconds to under one second per case in
   the measured diagnostic.

Only item 2 changes the optimization domain for the 2023 PRSS cases. Items 3
and 4 are report corrections; items 1, 5 and 6 are input, solver-policy and
execution corrections respectively.

## Full-day execution results

### 2019-06-22 — 48 cases

| Measure | SCIP → HiGHS | SCIP → CLP |
|---|---:|---:|
| Cases complete / optimal | 48 / 48 | 48 / 48 |
| Solver seconds | 612.002 | 571.605 |
| Wall seconds | 692.517 | 649.606 |
| Independent absolute diagnostic maximum | 0.000118284 | 0.000118275 |
| CPLEX mapped values compared | 725,438 | 725,438 |
| Missing / extra identities | 0 / 0 | 0 / 0 |
| Above displayed precision | 3,187 | 3,230 |
| Maximum absolute CPLEX difference | 15.0 | 24.05941 |

CLP was 6.60% faster in solver time. HiGHS had fewer above-precision values
and the smaller worst difference. Summary values, bid results, reserve results
and branch-constraint results match at authority precision on the HiGHS path.
Most remaining counts are raw network-price differences and alternative
continuous generation/reserve allocations. The independent diagnostic fails
its deliberately strict 1×10⁻⁴ absolute objective threshold by about
1.83×10⁻⁵; the user-approved evidence boundary treats solver-reported optimum
as the solve criterion and retains this residual as a diagnostic.

Evidence:

- [`cplex-reference-paths-20190622.json`](cplex-reference-paths-20190622.json)
- [`cplex-reference-comparison-20190622.json`](cplex-reference-comparison-20190622.json)

### 2023-08-02 — 305 cases across 48 trading periods

The day contains 5–7 pricing scenarios per trading period. Two ordered shards
were run concurrently per pathway. Every boundary case has explicit source
generation-start data, so the shard boundary does not invent a predecessor
initialization.

| Measure | SCIP → HiGHS | SCIP → CLP |
|---|---:|---:|
| Cases complete / optimal | 305 / 305 | 305 / 305 |
| Retry count | 0 | 0 |
| Aggregate solver seconds | 3,818.083 | 3,533.316 |
| Parallel critical-path wall seconds | 2,356.065 | 2,188.676 |
| Independent absolute diagnostic maximum | 1.640415 | 0.264297 |
| CPLEX mapped values compared | 4,380,469 | 4,380,487 |
| Missing / extra CPLEX identities | 18 / 18 | 0 / 0 |
| Certified alternative differences | 18,771 | 18,970 |
| Above displayed precision | 61,856 | 62,497 |
| Maximum absolute CPLEX difference | 700,000 | 700,000 |

The 700,000 maxima are non-unique market-node constraint dual allocations, not
energy, power-balance or system-cost errors. The two independently repeated
SCIP MIP runs selected different discrete representations in 14 cases. Despite
that, pathway-to-pathway physical values differ by at most 1.904×10⁻⁸, and
only four cases have a node/reserve market-price difference above 1×10⁻⁴; the
maximum pathway market-price difference is 0.0692322 NZD/MWh.

CLP is 7.46% faster in aggregate solver time and 7.10% faster on the two-shard
critical path. Its speed advantage does not translate to uniform CPLEX
closeness:

| CPLEX surface | HiGHS above precision | CLP above precision | Maximum |
|---|---:|---:|---:|
| Branch constraints | 0 | 251 | 136.20519 (CLP) |
| Branch results | 16,659 | 15,970 | 18.87608 |
| Bus results | 15,748 | 16,433 | 18.87638 |
| Island results | 86 | 81 | 204.51716 (HiGHS) |
| Base node results | 28,775 | 28,867 | 0.494827 |
| Offer results | 6 | 466 | 32.0 |
| Published energy prices | 531 | 367 | 0.49680 |
| Published reserve prices | 2 | 1 | 0.00169 |
| Risk results | 10 plus 18/18 identities | 7 | 0.099276 (HiGHS) |
| Summary results | 25 | 40 | 1.640604 (HiGHS) |

The base-node count uses the full decimal precision present in the supplied
aggregate CSV, so even sub-mill cent differences count as above precision. Its
largest price difference is 0.494827 NZD/MWh at WPT1101 in TP36. The largest
published energy difference is also WPT1101 in TP36: CPLEX 776.12518 versus
PySPD 776.62198 NZD/MWh, an absolute difference of 0.49680 NZD/MWh (0.0640%).
The maximum base-node generation and load differences are only
3.33×10⁻⁵ MW and 4.04×10⁻⁵ MW respectively.

### WPT1101 CPLEX-parity correction

The table above records the immutable pre-correction full-day comparison. A
targeted six-case TP36 rerun now selects CPLEX's export-side marginal at the
passive zero-flow `ORO_WPT1.1` loss kink. The corrected arithmetic base-node
price is `773.0625328434725` versus CPLEX `773.0625333333334` (difference
`4.90e-7 NZD/MWh`). The corrected duration-weighted publication is
`776.1251883043195` versus CPLEX `776.12518` (difference `8.30e-6 NZD/MWh`).
All six SCIP MIP and HiGHS fixed-RMIP solves were optimal. See
[`wpt1101-cplex-parity-20230802.md`](wpt1101-cplex-parity-20230802.md).

The expanded ten-day analysis finds 16,632 CPLEX load-endpoint choices, of
which 16,376 have no nonzero node allocation and therefore affect only raw
reporting. The 256 node-projected observations are bounded and remain
explicit output-parity evidence; see
[`cplex-zero-flow-analysis-ten-days.md`](cplex-zero-flow-analysis-ten-days.md).

The HiGHS risk identity mismatch is a different risk-setter selection on an
equal maximum-risk surface; CLP selected the CPLEX setter for those rows. Large
island reserve-sharing differences similarly reflect different allocation on
flat faces and must not be described as row-exact parity.

Evidence:

- [`cplex-reference-paths-20230802-highs.json`](cplex-reference-paths-20230802-highs.json)
- [`cplex-reference-paths-20230802-clp.json`](cplex-reference-paths-20230802-clp.json)
- [`cplex-reference-comparison-20230802-highs.json`](cplex-reference-comparison-20230802-highs.json)
- [`cplex-reference-comparison-20230802-clp.json`](cplex-reference-comparison-20230802-clp.json)

## Qualification statement

The evidence supports these claims:

- both pathways solve the two designated full days completely and report an
  optimum for every SCIP MIP and fixed RMIP;
- both reproduce physical dispatch surfaces to practical numerical tolerance;
- SCIP → CLP is the faster tested pathway on both days; and
- SCIP → HiGHS has the stronger overall mapped-field agreement with CPLEX and
  remains the recommended default.

The evidence does **not** support claiming that either pathway produces all
the same results as CPLEX. Exact CPLEX parity remains open, particularly for
raw network duals, alternative reserve allocation/risk setters and the
identified published node-price differences.
