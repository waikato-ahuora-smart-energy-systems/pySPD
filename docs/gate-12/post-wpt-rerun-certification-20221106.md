# 2022-11-06 post-WPT1101 rerun certificate

## Certified outcome

The direct WPT1101 pricing defect is fixed. The complete 196-case canonical
prefix was rerun through PySPD and through pinned vSPD using the explicit
SCIP-MIP → fix discrete variables → HiGHS-RMIP reference path. All 196 GAMS
primary and pricing solves were optimal, and the GAMS matrix and independent
price checks passed.

Numerical price parity for 2022-11-06 is now certified under the documented
one-sided load-sensitivity convention. Complete E2E parity remains open only
at the known report-schema and unimplemented risk/summary-table boundary.

| Observable | GAMS | PySPD | Absolute difference | Result |
| --- | ---: | ---: | ---: | --- |
| raw bus 816 | 17.572622712126556 | 17.572622712126545 | 1.07e-14 NZD/MWh | Pass |
| raw bus 820 | 17.552852079426955 | 17.552852079426938 | 1.78e-14 NZD/MWh | Pass |
| node WPT1101 | 17.572622712126556 | 17.572622712126545 | 1.07e-14 NZD/MWh | Pass |
| fixed-RMIP objective | -2177.951866644149 | -2177.9518666441813 | 3.23e-11 NZD | Pass |
| TP35 published WPT1101 | 13.18203 | 13.18718 | 0.00515 NZD/MWh (0.03907%) | Convention-certified |

The direct price tolerance is `0.0001 NZD/MWh`; the fixed-RMIP objective
tolerance is `0.0001 NZD`.

## Evidence boundary

The generalized correction applies the documented one-sided `+1 MW load`
derivative at every passive zero-flow AC-loss leaf. The full rerun shows that
pinned GAMS/HiGHS does not select that same side of the kink consistently.
It selects the load side at WPT buses 816/820 but the opposite, also valid,
side at many unrelated leaves. PySPD therefore matches the stated price
convention while differing from solver-basis-dependent GAMS marginals at
those kinks.

The independent validator reconstructs the load-side derivative from the
source topology, first loss factors, zero-injection/zero-flow state, and
parent-bus marginal. It certifies 58 affected bus values and projects the one
material node delta (`KIN1009`) through the source allocation matrix with zero
residual. It then rebuilds the six-case weighted publications for TP15 and
TP35. TP15 `KIN1009`, TP35 `KIN1009`, and TP35 `WPT1101` all reproduce the
PySPD five-decimal result with zero residual.

The mapped report comparison covers 13,133 values with zero missing or extra
identities. Fifty-seven differences are certified and zero values remain above
Authority display precision. The result still reports failure because the
known eight risk/summary tables are unimplemented. Semantic comparison retains
only four `report-field` schema-boundary records—one per affected case—and has
zero unresolved numeric price differences.

No branch-name allow-list was introduced to force historical agreement. Such
an exception would reproduce one solver basis without establishing a market
pricing rule and would make the model less extensible.

## Hash-bound provenance

- Official input SHA-256: `282ac2abeaa2f0c7c6e26b967e2ba90289c0ba5a9e696b99069d11350d3037b8`
- Work item SHA-256: `660f0e53a089fde3226618e5dd6f7c6effd15453891301f17022e532faaca6de`
- PySPD commit: `5282e736274108ffa18326ea01a619d9ab07cf94`
- Pinned vSPD commit: `3360a91ebd48f2e3cbb52a5e6766d893011054be`
- Candidate bundle SHA-256: `6b01efdf84eacfac717a47df9927482316288e0b7ab2ccc5c645a1ed25ef1f71`
- Reference bundle SHA-256: `e824a75c89939ea250e0a63d81b75cd0bac81c613aadda6dcb07be4fa0a066f0`
- GAMS solve-record SHA-256: `c071f134ec9f5e85ca5aad43a330c3ae5d4aeda9808f17cdc5e3ff9438ba7788`
- Zero-flow convention certificate SHA-256: `fd15aeebabcbd844253e3ca565a33fe5d84b1f9d3a535dfacf44c6cdc5c2a2c7`
- Semantic result SHA-256: `0b2475ee65c2f29e1166bc5c06883aecf22c9e57b336d0eebac27d7b7ec460a3`
- Mapped report result SHA-256: `2d08c42fe56be5e518836abf37b414e2ba8ae2c6cdc3f112c96dce09475d19c4`

The machine-readable certificate is
[`post-wpt-rerun-certification-20221106.json`](post-wpt-rerun-certification-20221106.json).
The compact independent-price evidence index is
[`zero-flow-price-convention-20221106.json`](zero-flow-price-convention-20221106.json).

## Next acceptance action

Implement and compare the remaining risk and summary report tables, then close
the explicit Authority/PySPD report-schema crosswalk boundary. Pricing itself
no longer blocks the 2022-11-06 comparison.
