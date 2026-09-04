# 2023-09-22 TP11 native-SOS support certificate

## Result

The first TP11 dispatch mismatch is resolved against the supplied historical
CPLEX archive. The affected case is `211012023091700557` at
`22-SEP-2023 05:00`.

The earlier full-day process selected an economically inferior native SOS2
support while SCIP reported optimality at primal feasibility `1e-6`. Reducing
that native-support selection tolerance to `1e-7` produces:

| Observable | Earlier full-day path | Corrected path | CPLEX archive |
|---|---:|---:|---:|
| Fixed-RMIP objective (NZD) | 560071.53875354 | 560071.57017835 | — |
| NI SIR price (NZD/MWh) | 0.11000000 | 0.10349821 | 0.10350 |
| SI reference price (NZD/MWh) | 83.48284720 | 83.48929742 | 83.48930 |
| NI SIR cleared (MW) | 113.80725819 | 108.97400000 | 108.97400 |
| NI SIR received (MW) | 63.89274181 | 68.72600000 | 68.72600 |
| SI SIR shared (MW) | 64.40349370 | 69.40737398 | 69.40737 |
| System cost (NZD) | 8128.20024663 | 8128.16897626 | 8128.16898 |
| System OFV (NZD) | 68519442.60125354 | 68519442.63267835 | 68519442.63268 |

The corrected objective is better by `0.031424813671 NZD`. This is not an
analytic zero-flow price interval and no result-side acceptance rule is used.
The optimization state itself now matches the gold-standard quantities and
prices.

## Cross-checks

- A `1e-9` native-SOS prefix and an independent explicit interval-binary
  support challenge produce the same target prices as `1e-7`.
- Across all 47 canonical cases through the target, only the TP11 case changes
  relative to the earlier full-day stream.
- The final prefix has 47 optimal primary/fixed-RMIP paths, zero retries, and
  passes independent validation with maximum residual `1.46e-5`.
- The existing TP4 CPLEX-gold reserve-kink oracle passes unchanged.
- Runtime is 533.58 solver-seconds / 655.87 wall-seconds, versus 1,181.08 /
  1,310.43 seconds for the unconditional support challenge.

## Evidence

- Final prefix manifest:
  [`cplex-reference-paths-20230922-tp11-native-1e7.json`](cplex-reference-paths-20230922-tp11-native-1e7.json)
- Independent support proof:
  [`cplex-reference-paths-20230922-tp11-support-polish.json`](cplex-reference-paths-20230922-tp11-support-polish.json)
- Decision record:
  [`ADR-0023`](../adr/0023-strict-native-sos-support-with-guarded-fallback.md)
