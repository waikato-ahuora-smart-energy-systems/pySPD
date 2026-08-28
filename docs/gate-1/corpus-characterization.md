# Gate 1 corpus characterization

## Frozen execution profile

The 29 August 2026 corpus run used pinned vSPD v5.0.6 commit
`21b1cf33f5607399331dcb1c03270348def5ccc8`, GAMS 54.3.1, SCIP 10.0.3,
and HiGHS 1.14.0 on arm64 macOS. SCIP used `numerics/feastol = 1e-7`.
The fixed-discrete HiGHS RMIP used primal, dual, and residual tolerances of
`1e-9`. The evidence root is `/private/tmp/pyspd-gate1-final-v2`; the hashes in
[corpus-manifest.json](corpus-manifest.json) bind each uncommitted raw evidence
pack without redistributing third-party data.

## Results

All 38 primary SCIP MIPs and all 38 fixed-discrete HiGHS RMIPs reported normal
completion and optimal model status. All ten final matrices passed independent
activity, row-bound, column-bound, regular-stationarity, scaled-stationarity,
and free-column guard checks. All 20,344 reconstructed prices matched native
GDX values and their five-decimal published CSV values; 38 of those prices were
reconstructed through the independent multi-hop dead-node price-transfer
algorithm.

| Run | Input SHA-256 prefix | MIP/RMIP pairs | Prices | Transfers | Raw stationarity max | Scaled stationarity max | Reports | Qualified |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| AUD RTD 2025-02-26 11:55 | `f010065a800a` | 1 | 534 | 0 | `1.19e-9` | `5.91e-13` | 20 | Yes |
| PRSS 2022-11-01 00:00 | `3611953aeea7` | 8 | 4,184 | 0 | `7.34e-5` | `6.72e-10` | 13 | Yes |
| PRSS 2025-01-14 21:00 | `a3fdb53a8bf3` | 8 | 4,344 | 16 | `3.16e-9` | `5.29e-12` | 13 | Yes |
| PRSS 2025-01-27 10:00 | `be6d09a880db` | 8 | 4,344 | 8 | `7.51e-10` | `2.48e-14` | 13 | Yes |
| PRSS 2025-02-26 11:30 | `2ee2d560a8c9` | 8 | 4,272 | 8 | `4.03e-9` | `2.31e-12` | 13 | Yes |
| RTD 2022-11-01 13:00 | `2e21665f55aa` | 1 | 523 | 0 | `4.50e-11` | `1.28e-14` | 13 | Yes |
| RTD 2022-11-01 13:05 | `33ffbf917e2a` | 1 | 523 | 0 | `1.32e-11` | `2.72e-15` | 13 | Yes |
| RTD 2025-02-19 23:50 | `89cbc5157eec` | 1 | 543 | 3 | `5.16e-10` | `2.44e-13` | 13 | Yes |
| RTD 2025-02-19 23:55 | `f4c73f681d3b` | 1 | 543 | 3 | `1.14e-11` | `6.06e-15` | 13 | Yes |
| SPD RTD 2025-02-26 11:55 | `f010065a800a` | 1 | 534 | 0 | `1.19e-9` | `5.91e-13` | 13 | Yes |

The 2023 pack is fully hash-bound and classified provenance-only because it
targets the deferred RTP v4 conformance profile. Of the twelve 2025 inputs,
nine RTD/PRSS inputs are in scope and executed above; two NRSS inputs and one
NRSL input are explicitly deferred by the first-release scope.

## Official secondary comparisons

Official files were treated as CPLEX-produced secondary comparators, not as the
active SCIP/HiGHS oracle. Keys and record counts matched exactly. Price
differences are therefore classified solver-profile/basis differences under
ADR-0008 and are not averaged into active-profile acceptance thresholds.

| Official case | Records | Values different at published precision | Maximum absolute difference (NZD/MWh) |
|---|---:|---:|---:|
| RTD 2022-11-01 13:00 | 523 | 163 | 1.2357 |
| RTD 2022-11-01 13:05 | 523 | 164 | 4.5527 |
| RTD 2025-02-19 23:50 | 543 | 534 | 299.1409 |
| RTD 2025-02-19 23:55 | 543 | 168 | 0.3353 |
| PRSS 2022-11-01 00:00 | 4,184 | 1,857 | 5.1062 |
| PRSS 2025-01-14 21:00 | 4,344 | 2,503 | 78.8155 |
| PRSS 2025-01-27 10:00 | 4,344 | 2,130 | 111.9293 |
| RTD 2025-02-26 11:55 | 534 | 170 | 184.79089 |
| PRSS 2025-02-26 11:30 | 4,272 | 2,525 | 57.48106 |

The old combined official price file is ambiguous for duplicate NRSS/PRSS
timestamps. Comparisons above use the official `NodeResults_TP.csv`, whose
`CaseID` makes the identity explicit. Dedicated new-case published-price files
were compared directly.

## Population qualification boundary

This execution closes recovery and classification of the named 2023 and 2025
packs and supplies ordinary controls. The separate Gate 1 evidence binds all
139 corrected shortfall dates, an exact optimal affected transfer/max-loop/
cleanup fixture, and selected 46- and 50-period daylight-saving cases. ADR-0010
accepts that package for Gate 1 while leaving exact identification and replay of
all 546 intervals mandatory at Gate 8.
