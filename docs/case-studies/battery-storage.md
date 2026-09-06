# Multi-period battery-storage study

PySPD now includes a minimal, explicitly separate multi-period battery research
profile. It demonstrates genuine time coupling without changing the validated
single-period vSPD compatibility model.

:::{admonition} Research profile
:class: warning

`pyspd-multiperiod-battery-v1` is an analytic research foundation. It is not
registered in the production `pyspd run` application, does not read battery
assets from vSPD GDX, and has not passed historical market parity. Its prices
are LP energy-balance duals, not qualified vSPD published prices.
:::

## Minimal example

The following two-period case has free capacity from a NZD 10/MWh offer in the
first hour and a NZD 100/MWh offer serving 10 MW in the second hour:

```python
from pyspd.multiperiod import (
    BatteryAsset,
    BatteryStudyRunner,
    MultiPeriodCase,
    Period,
    PeriodOffer,
)

case = MultiPeriodCase(
    case_id="two-period-arbitrage",
    periods=(
        Period("P1", duration_hours=1.0, demand_mw=0.0),
        Period("P2", duration_hours=1.0, demand_mw=10.0),
    ),
    offers=(
        PeriodOffer("P1", "GEN", capacity_mw=10.0, price_per_mwh=10.0),
        PeriodOffer("P2", "GEN", capacity_mw=10.0, price_per_mwh=100.0),
    ),
    batteries=(
        BatteryAsset(
            "BAT",
            power_capacity_mw=10.0,
            energy_capacity_mwh=10.0,
            initial_energy_mwh=0.0,
            terminal_energy_mwh=0.0,
        ),
    ),
)

result = BatteryStudyRunner().run(case)
print(result.objective_nzd)
print(dict(result.charge_mw))
print(dict(result.discharge_mw))
```

The verified result costs NZD 100: 10 MW is generated and charged in P1, then
10 MW is discharged in P2. The no-battery control costs NZD 1,000.

## Algebra

For battery (b) and ordered period (t), stored energy follows:

```text
E[t,b] = E[t-1,b]
         + duration[t] * (charge_efficiency[b] * charge[t,b]
         - discharge[t,b] / discharge_efficiency[b])
```

The first row uses declared initial energy. The last period is constrained to
the declared terminal energy. Charge plus discharge cannot exceed battery
power capacity, and stored energy is bounded by energy capacity.

System energy balance is:

```text
generation[t] + discharge[t] = demand[t] + charge[t]
```

The objective minimizes duration-weighted generation offer cost and optional
battery throughput cost. There are no binary charge/discharge modes in v1;
nonnegative energy prices, physical losses, and/or a positive throughput cost
should prevent economically pointless cycling. Studies with negative offers or
subsidies must explicitly test for simultaneous charge and discharge.

## Class-based structure

The formulation is assembled from independently owned components:

1. `MultiPeriodDomainsComponent` — ordered periods, duration, and demand;
2. `MultiPeriodBatteryComponent` — charge, discharge, stored energy, power,
   temporal balance, and terminal state;
3. `MultiPeriodGenerationComponent` — period-specific generator offers;
4. `MultiPeriodBalanceComponent` — system energy balance; and
5. `MultiPeriodObjectiveComponent` — production and throughput costs.

The ordinary `ModelAssembler` checks ownership, dependencies, version support,
and produces the semantic structural signature. `MultiPeriodSolvePolicy` uses
one-thread HiGHS simplex. Pricing, result collection, and rendering remain
separate extension classes.

## Current validation

The analytic tests establish:

- exact two-period dispatch and a 90% cost reduction against the no-battery
  control;
- initial, transition, terminal, energy-capacity, and power-capacity behavior;
- energy and storage residuals below `1e-8`;
- finite LP balance duals;
- deterministic repeated model structure; and
- fail-closed period, offer, efficiency, power, and energy validation.

## Before a historical battery study

Historical market integration requires:

1. a hash-bound battery source schema with node, commissioning date, power,
   usable energy, losses, initial/terminal policy, and operating cost;
2. a mapping into the full AC/HVDC/reserve formulation rather than the current
   single-bus analytic balance;
3. 46-, 48-, and 50-period input adapters and terminal-state sensitivity;
4. charging demand and discharging generation at the correct electrical node;
5. FIR/SIR capability, risk treatment, and mutually exclusive operating modes
   if the study requires them;
6. fixed-discrete RMIP pricing rules for any binary battery decisions;
7. hand-checkable loss and capacity fixtures; and
8. a historical baseline/no-battery control before interpreting benefits.

This progression keeps the multi-period architecture reusable for later hydro
budgets, flexible demand, EV charging, and unit-commitment components.
