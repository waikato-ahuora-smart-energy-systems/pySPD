# 2022-11-06 native-SOS regression

The complete 196-case PySPD prefix was rerun after ADR-0019 changed the v5
application boundary to native SCIP SOS2 state. Every primary MIP and
fixed-state HiGHS RMIP solve reported optimal. All four affected cases retain
complete parity against the unchanged pinned-GAMS bundle.

All 48 semantic case-surfaces pass with zero unresolved differences. The
maximum fixed-RMIP objective difference is `1.37e-11 NZD`. The regenerated
independent zero-flow certificate passes for 58 buses, one node projection,
and two publications. All 13 Authority report tables and 68,558 mapped values
pass under the version-5 report profile, with 254 classified differences and
no above-precision, missing, extra, or unimplemented values.

This supplements rather than rewrites the original
[`2022-11-06 post-WPT certificate`](post-wpt-rerun-certification-20221106.md).
The machine-readable regression index is
[`native-sos-regression-20221106.json`](native-sos-regression-20221106.json).
