# ADR-0031: Introduce storage as a separate multi-period research profile

| Field | Decision |
|---|---|
| Status | Accepted by explicit project direction |
| Date | 2026-09-06 |
| Decider | Project owner direction to implement case-study item 4 |

## Context

The qualified vSPD application solves pricing cases independently. Combining
separable cases in one Pyomo model was slower and added no economic information.
Storage is different: its state of charge creates a genuine equation between
periods. Adding that equation silently to the compatibility formulation would
change dispatch, prices, model identity, and validation claims.

## Decision

Implement `pyspd-multiperiod-battery-v1` as an explicit research formulation.
It uses immutable ordered-period, offer, and battery data and is assembled from
separate domain, generation, battery, balance, and objective components through
the existing owner-checked `ModelAssembler`.

The battery component owns charge, discharge, stored energy, combined power
limits, inter-period conservation, and terminal state. The first profile is a
continuous LP solved with HiGHS simplex. It has separate pricing, result, and
report services and is not registered in the production vSPD application.

## Consequences

The minimal analytic model can prove the reusable time-coupling architecture
without asserting historical NZEM fidelity. It supports multiple batteries and
arbitrary positive period durations but currently has one system balance, no
network, no reserve, no degradation state, and no binary operating mode.

Any later integration with the full market model is a new formulation version
and must define node mapping, reserve participation, terminal policy, pricing,
historical source data, and validation.

## Rejected alternatives

- Treating storage periods as independent was rejected because it cannot
  conserve stored energy.
- Adding storage flags to `vspd-v5.0.6-reserve` was rejected because it would
  invalidate compatibility claims.
- Reusing the experimental separable vectorized model was rejected because the
  new foundation should contain only explicit inter-period ownership.
- Adding binary charge/discharge state to the first fixture was deferred until
  the continuous conservation and pricing surface is validated.

## Verification

The hand-checkable two-period case reduces cost from NZD 1,000 to NZD 100 by
moving 10 MWh from a NZD 10/MWh period to a NZD 100/MWh period. Tests require
the exact primal solution, balance and storage residuals below `1e-8`, finite
duals, deterministic structural signatures, component build order, and
fail-closed physical input validation.

## Revisit triggers

Revisit before adding network nodes, reserve, degradation, binary modes,
rolling horizons, persistent solves, historical GDX adapters, or production CLI
registration.
