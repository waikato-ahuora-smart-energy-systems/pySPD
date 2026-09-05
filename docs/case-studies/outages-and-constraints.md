# Generation and transmission outages

These recipes alter existing source records with the [audited scenario
API](../user-guide/audited-scenarios.md). They do not add new network objects.

## Generator commercial withdrawal

To remove an offer from dispatch, set every existing energy `limitMW` tranche
to zero for the intended scope. Also set every existing reserve tranche to zero
if the unit must be unavailable for FIR and SIR.

```python
from pyspd.orchestration import (
    OverrideFamily,
    OverrideInstruction,
    OverrideScope,
)

offer = "HLY2201 HLY4"
energy = tuple(
    OverrideInstruction(
        OverrideFamily.ENERGY_OFFER,
        OverrideScope.TRADING_PERIOD,
        "TP18",
        (offer, "limitMW", f"t{block}"),
        0.0,
    )
    for block in range(1, 21)
)
reserve = tuple(
    OverrideInstruction(
        OverrideFamily.RESERVE_OFFER,
        OverrideScope.TRADING_PERIOD,
        "TP18",
        (offer, reserve_class, reserve_type, "limitMW", f"t{block}"),
        0.0,
    )
    for reserve_class in ("FIR", "SIR")
    for reserve_type in ("PLRO", "TWRO", "ILRO")
    for block in range(1, 21)
)
instructions = energy + reserve
```

The override layer can append zero-valued records for absent tranches. For a
minimal audit, first inventory the offer's existing energy and reserve records
and emit instructions only for those identities.

This is an offer withdrawal, not a complete physical generator-outage model.
Initial generation, primary/secondary mappings, ramp limits, and risk-setter
status may remain active. A physical outage requires a source transformation
covering all of those semantics and must be validated against the corresponding
vSPD/GAMS setup.

Inspect:

- energy and reserve shortfall;
- replacement generation and reserve;
- risk setters and covered quantities;
- island reference prices and node prices;
- HVDC transfer and losses; and
- ramp-rate violations caused by nonzero initial generation.

## Branch derating

Set one directional capacity for a trading period:

```python
instruction = OverrideInstruction(
    OverrideFamily.BRANCH_PARAMETER,
    OverrideScope.TRADING_PERIOD,
    "TP18",
    ("BEN_HAY1.1", "forwardCap"),
    250.0,
)
```

Use a paired `reverseCap` instruction when both directions change. Setting both
capacities to zero forces zero transfer while leaving the branch in the model;
it is not the same as removing the branch from topology. Fixed-loss and outage
metadata still follow the input GDX.

Compare `branch.csv` flows, losses, endpoint prices, rentals and nearby node
prices. Check whether another parallel path becomes binding.

## Security-constraint sensitivity

Change an existing branch-group constraint limit:

```python
instruction = OverrideInstruction(
    OverrideFamily.BRANCH_CONSTRAINT_RHS,
    OverrideScope.CASE_ID,
    "211012023091330496",
    ("BRANCH_CONSTRAINT_ID", "cnstrLimit"),
    350.0,
)
```

`BRANCH_CONSTRAINT_FACTOR` changes one branch coefficient with target
`(constraint, branch)`. Market-node constraints have corresponding RHS and
factor families. For an energy factor, use
`(constraint, offer, "NA", "NA")`; reserve factors use their actual reserve
class and type.

Predeclare whether the study changes only a limit or also its coefficients.
Changing both without separate scenarios makes causal interpretation difficult.

## N-1 and contingency batches

For an N-1 screen, generate one immutable scenario record per component and
run the same baseline case population. Aggregate:

- solve success and violation flags;
- maximum deficit or surplus by family;
- system-cost change;
- maximum node-price separation;
- overloaded/binding branch identities; and
- reserve/risk changes.

Do not treat a zero-capacity branch study as a validated topology-contingency
study unless equivalence to source outage semantics has been demonstrated.
