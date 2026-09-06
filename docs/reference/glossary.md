# Glossary

These terms describe the boundaries used throughout the PySPD documentation.

| Term | Meaning in PySPD |
|---|---|
| SPD | Scheduling, Pricing, and Dispatch: the New Zealand electricity market model implemented here under explicit version profiles. |
| vSPD | The reference virtual SPD model used for historical replay and comparison. A vSPD version is distinct from a PySPD formulation ID. |
| GDX | GAMS Data eXchange input, read through GAMS Transfer and validated against a versioned symbol catalog. |
| Input schema | The declared source-data contract and any adapter, such as `vspd-v3-final-pricing`. |
| Formulation | A named set of algebra, preprocessing, solve, pricing, and result contracts, such as `vspd-v5.0.6-reserve`. |
| Case | One source pricing scenario identified by a case ID, datetime, and trading-period mapping. |
| Trading period | A source market-period identity. Multiple cases can contribute to its published price. |
| MIP | Mixed-integer programming solve used to select dispatch and discrete/SOS support. |
| SOS | Special ordered set. The selected support is retained at the pricing boundary. |
| Fixed RMIP | The continuous pricing solve after the selected discrete/SOS state is fixed; PySPD's default uses HiGHS. |
| Dual / marginal | A constraint's marginal objective value at the solved continuous model. A raw dual is not necessarily the final published market price. |
| FIR / SIR | Fast instantaneous reserve / sustained instantaneous reserve. |
| HVDC | High-voltage direct-current transmission, represented separately from the AC network. |
| Bus / node | Network-balance location / market-node identity. Source allocation factors map bus prices to nodes. |
| Published price | A price aggregated using source publication durations and the configured rounding boundary. |
| Analytical interval | An independently justified range of valid marginals at a non-differentiable or degenerate point. |
| Oracle | A reference execution or retained result used as comparison evidence, with explicit source and environment provenance. |
| Parity | Agreement on a declared population, identity set, output surface, and numerical convention. |
| Manifest | A machine-readable record binding artifacts and metadata through SHA-256 hashes. |

Continue with [results and prices](../user-guide/results.md) for price surfaces
or [interpreting parity](../validation/interpreting-parity.md) for comparison
rules.
