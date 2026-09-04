# 2023-09-22 TP24 equal-price energy allocation

## Outcome

The TP24 11:30 CPLEX/PySPD difference is an economically and physically
equivalent allocation, not an objective or price mismatch. Both solutions
clear 55 MW from the three TUI1101 offers. PySPD moves 3.486 MW from
`TUI1101 TUI0` to `TUI1101 PRI0` relative to the archive.

The source GDX proves that the complete transferred quantity lies in each
offer's second energy block, and both blocks cost exactly 210.07 NZD/MWh:

| Offer | CPLEX MW | PySPD MW | First block | Second block |
|---|---:|---:|---:|---:|
| `TUI1101 PRI0` | 13.800 | 17.286 | 13.8 MW @ 0.001 | 8.2 MW @ 210.07 |
| `TUI1101 TUI0` | 23.200 | 19.714 | 18.5 MW @ 0.001 | 16.5 MW @ 210.07 |

The two offer nodes have zero load. Their allocation factors project the
change onto buses 303–307. Each leaf bus connects to common bus 308 through
one of `TUI_T1.T1`–`TUI_T5.T5`; every affected transformer has zero fixed
loss, zero dynamic-loss factor in both directions, a 2,000 MW directional
limit, and no branch-security coefficient. The five flow changes are exactly
the allocation-weighted injection changes, while their sum at bus 308 is zero.
Prices, losses, rentals, island totals, reserve, and objective outputs are
unchanged at their governed precision.

## Acceptance boundary

The certificate admits exactly fourteen identities: two offer-generation
rows, five bus-generation rows, five branch-flow rows, and the two derived
daily node-generation rows. It cannot certify prices, losses, reserve,
objectives, unrelated offers, or another case. Its hashes bind the input GDX,
six-case benchmark stream, benchmark manifest, and four CPLEX result files.

The immutable evidence is
[`cplex-tp24-energy-allocation-20230922.json`](cplex-tp24-energy-allocation-20230922.json).

## Complete-day application

The same fourteen identities are separately hash-bound to the latest complete
274-case stream by
[`cplex-tp24-energy-allocation-20230922-full-day.json`](cplex-tp24-energy-allocation-20230922-full-day.json).
Applying it to all 3,964,736 mapped values increases certified differences
from 10,044 to 10,058 and decreases above-precision differences from 29,631
to 29,617. No other table count changes. The complete comparison remains
fail-closed because it predates later targeted corrections and still contains
the broader known price, reporting, and identity population; the TP24
allocation itself is fully certified. The durable result is
[`cplex-reference-comparison-20230922-highs-root-boundary-interval-tp24-allocation.json`](cplex-reference-comparison-20230922-highs-root-boundary-interval-tp24-allocation.json).
