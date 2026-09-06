# SPD v16 delta and traceability register

The authoritative formulation PDF governs intent. The Electricity Authority
feature branch supplies readable executable behavior and representative 2026
GDX inputs. Where those sources do not demonstrably agree, the difference is
retained rather than silently normalized.

| ID | v16 behavior | PySPD owner | Focused evidence | Status |
|---|---|---|---|---|
| `V16D-001` | Cap offer blocks during preprocessing before equal-price comparison | `capped_offer_blocks`; `Spd16SourcePreprocessor` | cap and source-order boundary tests | Implemented |
| `V16D-002` | Same-price, same-bus offer blocks clear proportionally, with `0.0001` tie slack | `Spd16TieBreakComponent`; `Spd16ReserveEconomicsComponent` | pair construction, denominator, assembly, validator tests | Implemented |
| `V16D-003` | Matched charge/discharge battery units cannot operate concurrently | `derive_battery_pairs`; `Spd16BatteryModeComponent` | matching and binary-mode analytic tests | Implemented |
| `V16D-004` | Ambiguous multi-pair battery matches are excluded | `derive_battery_pairs` | adversarial ambiguity test | Implemented from formulation PDF |
| `V16D-005` | Pricing RMIP fixes the v16 battery binary | v16-aware oracle overlay; shared solve policy | discovered-defect regression and optimal MIP/RMIP oracle run | Implemented |
| `V16D-006` | `ACCELink` and `ACECELink` are explicit link-risk classes | `Spd16Case`; `Spd16ReserveRiskComponent` | risk-domain and assembly tests | Implemented |
| `V16D-007` | Sharing/shortfall adjustments apply in reserve requirement, not gross risk | `Spd16ReserveRiskComponent`; `Spd16ReserveRequirementComponent` | component ownership and equation tests | Implemented |
| `V16D-008` | Zero-cleared island reserve price is the sum of applicable requirement marginals | `Spd16PricingEngine` | zero/nonzero analytic price tests | Implemented |
| `V16D-009` | CE reserve-deficit penalty is omitted; ECE remains | `Spd16ReserveEconomicsComponent` | objective-component tests | Implemented |
| `V16D-010` | Bad-price replacement factor changes from 5 to 3 | `Spd16ModelPreprocessor`; application postprocessor selection | profile-selection tests | Implemented |
| `V16D-011` | v16 has a separate result/report contract | `Spd16ResultSchema`; `Spd16ReportRenderer`; registry | class-composition and application tests | Implemented |
| `V16D-012` | Source schema adds `i_busUnitAndKey3Match` | `SymbolCatalog.spd_v16` | exact 44-symbol and missing-symbol tests | Implemented |

## Cross-version worked cases

- A source dated 22 June 2026 is rejected by the v16 compatibility policy; a
  source dated 23 June 2026 is accepted. Selecting v5 remains explicit and does
  not trigger v16 behavior by date.
- Two positive capped blocks at the same bus and price create one normalized
  proportional-clearing relationship only in v16. The v5 assembly fingerprint
  remains `592a972925b1d4b44d3253d7dd8f1a7c1ccdfa857b48b7b3aabb844837c47801`.
- A uniquely matched battery pair creates one binary charging-mode decision.
  Multiple matches trigger the formulation-document safeguard and create no
  pair.
- At zero cleared reserve, v16 publishes the sum of reserve-requirement duals;
  at nonzero reserve it publishes the island-reserve-definition dual.

## Source discrepancy and interpretation

The formulation PDF specifies the multi-pair ambiguity safeguard. The inspected
public feature source did not provide demonstrable equivalent logic. PySPD
follows the formulation document and records the discrepancy here. This is not
silently treated as oracle parity.

## Known qualification differences

On the representative RTD input, the Authority feature oracle objective is
`224118715.5243`; the Pyomo portable solve objective is
`224118723.3571185`, a difference of approximately `7.8328185`. The published
reserve prices also differ. Both implementations report optimal and pass their
independent feasibility/matrix checks, but the differences are unresolved for
strict compatibility. Gate 12 owns their algebraic, basis, pricing, and report
resolution. Gate 11 therefore authorizes the versioned engineering profile,
not parity.

