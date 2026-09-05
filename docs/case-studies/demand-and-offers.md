# Demand and offer studies

These studies use the [audited scenario API](../user-guide/audited-scenarios.md).

## Demand scaling

Scale North Island conforming demand by 5% in TP18:

```python
from pyspd.orchestration import (
    OverrideFamily,
    OverrideInstruction,
    OverrideScope,
)

instruction = OverrideInstruction(
    OverrideFamily.DEMAND,
    OverrideScope.TRADING_PERIOD,
    "TP18",
    ("ISLAND", "NI", "CONFORMING", "SCALE"),
    1.05,
)
```

Other valid demand targets are:

- `("ALL", "ALL", "ALL", "SCALE")` for a system-wide multiplier;
- `("NODE", "HAY2201", "ALL", "INCREMENT")` for a node MW change; and
- `("ISLAND", "SI", "NONCONFORM", "VALUE")` for a total group value
  allocated over nodes with positive original load.

For group `INCREMENT` and `VALUE`, PySPD distributes the delta in proportion to
positive baseline demand. A node target changes the selected node directly.

Recommended metrics include system cost, generation by offer/island, AC and
HVDC losses, node prices, FIR/SIR requirements and prices, shortfalls, and
binding constraint count.

## Demand sweep

Use predeclared multipliers such as `0.90`, `0.95`, `1.00`, `1.05`, and `1.10`.
The `1.00` scenario should reproduce the baseline hashes or numerical values;
it is a useful pipeline control. Give every multiplier a deterministic scenario
ID and output directory.

Do not infer a marginal demand response across a point where a unit, reserve
risk, loss segment, or scarcity tranche changes state. Plot piecewise results
and retain the discrete-state transition.

## Energy offer price

Change tranche `t1` for one offer and one case:

```python
instruction = OverrideInstruction(
    OverrideFamily.ENERGY_OFFER,
    OverrideScope.CASE_ID,
    "211012023091330496",
    ("HLY2201 HLY4", "price", "t1"),
    125.0,
)
```

Use `limitMW` instead of `price` to change tranche capacity. The target order is
`(offer, component, tranche)` even though the underlying GDX dimension order is
different; `OverrideApplier` performs the governed mapping.

## Ramp and offer parameters

An offer-parameter instruction can change an existing source component:

```python
instruction = OverrideInstruction(
    OverrideFamily.OFFER_PARAMETER,
    OverrideScope.TRADING_PERIOD,
    "TP18",
    ("HLY2201 HLY4", "rampUpRate"),
    30.0,
)
```

Parameter names are case-sensitive source identifiers such as `rampUpRate`,
`rampDnRate`, `dispatchable`, `initialMW`, or `resrvGenMax`. Confirm the symbol
exists and has the intended units before changing it. Ramp inputs are normalized
by the selected input adapter; a historical v3 source must use its declared
schema so MW/minute and MW/hour are not confused.

## Interpreting results

An offer change may alter reserve as well as energy because the model is
co-optimized. Check `offer.csv`, `reserve.csv`, `risk.csv`, and network flows
together. A price change with unchanged total cost can be a valid dual-basis
change; a dispatch or objective change requires a physical/economic explanation.
