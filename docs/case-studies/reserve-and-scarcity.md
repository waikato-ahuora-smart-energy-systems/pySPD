# Reserve and scarcity studies

## Reserve offer price or quantity

Change an existing FIR PLRO tranche:

```python
from pyspd.orchestration import (
    OverrideFamily,
    OverrideInstruction,
    OverrideScope,
)

price_instruction = OverrideInstruction(
    OverrideFamily.RESERVE_OFFER,
    OverrideScope.TRADING_PERIOD,
    "TP18",
    ("HLY2201 HLY4", "FIR", "PLRO", "price", "t1"),
    1.50,
)

quantity_instruction = OverrideInstruction(
    OverrideFamily.RESERVE_OFFER,
    OverrideScope.TRADING_PERIOD,
    "TP18",
    ("HLY2201 HLY4", "FIR", "PLRO", "limitMW", "t1"),
    20.0,
)
```

Valid classes are `FIR` and `SIR`; source reserve types include `PLRO`, `TWRO`,
and `ILRO`. Change only identities that exist in the selected GDX unless the
study explicitly governs domain expansion.

Track reserve cleared by offer, island requirements, sharing and receipt,
effective CE/ECE quantities, risk setters, reserve violations, energy dispatch,
and both island prices. Reserve and energy are co-optimized, so an apparently
reserve-only change can alter energy and HVDC flow.

## Reserve availability

Set all relevant `limitMW` values to zero to remove one reserve product from an
offer while retaining its energy offer. This answers a different question from
a complete generator withdrawal and should use a distinct scenario name.

A useful sweep removes:

1. FIR PLRO only;
2. all FIR types;
3. SIR only; and
4. all reserve while retaining energy.

Compare each with the unchanged baseline, not only with the preceding sweep
member.

## Risk and requirement changes

The current override families do not provide a general direct editor for every
risk, reserve-requirement, HVDC-loss, or scarcity symbol. For those studies:

1. create a typed transformation of the raw GDX symbols;
2. validate it against the appropriate `SymbolCatalog`;
3. record before/after logical hashes and a conservation/domain ledger;
4. run a focused matrix and finite-difference test; and
5. only then execute the case population.

Do not disguise a risk or scarcity change as a reserve-offer change. The two
experiments alter different model equations.

## Scarcity studies

Existing historical scarcity or shortfall cases can be replayed directly with
the stable CLI. Check `summary.csv` violation quantities, `risk.csv` shortfall,
and the relevant scarcity-price blocks before interpreting capped prices.

Creating a new scarcity regime requires changing the source activation,
tranche limit, and price records together. That transformation is not exposed
as a stable CLI scenario today. Implement it as a named, versioned extension
with probity tests rather than editing a CSV result after solving.

## Price intervals at reserve kinks

Reserve-loss breakpoints and zero-priced surplus reserve can produce multiple
valid duals. Where PySPD has independently verified both one-sided marginals,
`reserve.csv`, `island.csv`, and `published_price.csv` contain a closed
`price_interval`. Reference containment is then the correct test.

If the interval field is empty, a different solver price is unresolved unless
another governed certificate explains it. Solver success alone does not create
an analytical interval.
