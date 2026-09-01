# 2023-01-17 replay certification

The second complete paired date passes under the governed portable solver
path: SCIP solves the MIP, every discrete and SOS decision is fixed, and HiGHS
solves the resulting RMIP for prices. Both engines completed the canonical
191-case prefix through the affected interval; every primary and pricing solve
reported an optimum.

The affected interval is `171012023010355022` at 16:55. Exact JSON comparison
is intentionally diagnostic because the two implementations have different
sparse and report representations. The governed semantic comparison passes
all twelve surfaces with zero failed surfaces and zero unresolved differences.

The only material price-convention differences are at zero-flow topology
boundaries. The independent load-derivative validator certifies 49 bus prices,
projects the three material nodes `GOR2202`, `OTA2202`, and `WPT1101` with zero
node residual, and reconstructs their TP34 publications to within
`0.00002 NZD/MWh`. The largest node-price difference is
`0.11549769467476 NZD/MWh` at `WPT1101`; it is a certified one-sided derivative
choice, not an objective or physics mismatch.

All 13 Authority report tables are implemented. The mapped-row comparison
checks 17,203 values with zero missing or extra identities, zero values above
the governed precision, and zero unimplemented tables. It classifies 270
bounded differences, including the independent zero-flow evidence and the
portable published-price tolerance established by
[ADR-0018](../adr/0018-portable-published-price-report-tolerance.md).

This certifies the complete 2023-01-17 paired comparison. It does not close
Gate 12: population enumeration, further representative days, repeat/resume,
the deferred strict CPLEX profile, and the final evidence index remain open.

The machine-readable evidence index is
[`replay-certification-20230117.json`](replay-certification-20230117.json).
