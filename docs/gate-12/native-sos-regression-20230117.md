# 2023-01-17 native-SOS regression

The complete 191-case PySPD prefix was rerun after ADR-0019 changed the v5
application boundary to native SCIP SOS2 state. Every primary MIP and
fixed-state HiGHS RMIP solve reported optimal on its first attempt. The
affected case `171012023010355022` at 16:55 retains complete parity against the
unchanged pinned-GAMS bundle.

All twelve semantic surfaces pass with zero unresolved differences. The
fixed-RMIP objective differs by only `2.91e-11 NZD`. The regenerated independent
zero-flow certificate passes for 49 buses, three nodes, and three publications.
All 13 Authority report tables and 17,203 mapped values pass under the
version-5 report profile, with 104 classified differences and no above-precision,
missing, extra, or unimplemented values.

This supplements rather than rewrites the original
[`2023-01-17 replay certificate`](replay-certification-20230117.md). The
machine-readable regression index is
[`native-sos-regression-20230117.json`](native-sos-regression-20230117.json).
