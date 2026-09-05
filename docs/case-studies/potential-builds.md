# Potential case studies to build

This page is a development portfolio, not a claim that every study is already
implemented. It separates studies that can be assembled from the current
audited scenario surface from studies that need new, versioned model algebra.
That distinction matters: a counterfactual input change can reuse a qualified
formulation, while a new constraint, decision variable, time coupling, or price
rule creates a new formulation that needs its own validation evidence.

## Portfolio at a glance

| Candidate study | Research question | Build class | Main extension | Suggested first evidence |
|---|---|---|---|---|
| Residential PV replication | How does distributed PV adoption affect dispatch, prices, hydro generation, and emissions? | Planned research profile | Audited nodal PV-demand overlay and paper metrics | Reproduce the paper's baseline date and one adoption case |
| Generator or circuit outage replay | Which assets drive cost, congestion, reserve, and price separation during stressed periods? | Can start now | Scenario catalogue and event metrics | One historical event with a no-change control |
| Demand and offer elasticity | How do dispatch and prices respond to load, offer-price, or capacity changes? | Can start now | Experiment runner and sweep summaries | A small preregistered sweep around one qualified day |
| Battery energy storage | What are the energy, reserve, congestion, and price effects of storage? | New formulation | State of charge, charging, efficiency, terminal state, reserve coupling | Two-period analytic case, then a 48-period historical day |
| Flexible demand and EV charging | What is the value of shifting demand across trading periods? | New formulation | Inter-period energy/service constraints and consumer objective | Small load-shifting unit test, then a daily fleet case |
| Hydro energy budget | How does limited water alter dispatch, prices, and thermal displacement? | New formulation | Inter-period energy budget or reservoir balance | Two-period water-value case, then a dry-day study |
| Thermal unit commitment | What changes when start-up, minimum-run, and minimum-down decisions are represented? | New formulation | Commitment state, start-up cost, minimum up/down time | Three-period analytic case and matched MIP benchmark |
| Renewable uncertainty | How robust is dispatch to wind, solar, demand, or outage uncertainty? | New formulation family | Scenario tree or robust constraints and probability data | Tiny two-scenario extensive form with hand-checked optimum |
| Transmission reinforcement | Which branch upgrades reduce congestion and total production cost? | Mixed | Existing capacity overrides for screening; investment decisions for expansion | Capacity sweep before any endogenous investment model |
| Reserve-policy design | What is the cost and security effect of alternative reserve requirements or products? | Mixed | Existing requirement inputs for sensitivities; new products need formulation changes | One requirement sweep with risk-setter diagnostics |
| Carbon-price and emissions study | How do emissions prices change offers, dispatch, prices, and emissions? | Data/profile extension | Generator emissions factors and audited offer-cost transformation | Baseline mass balance and a zero-carbon-price control |
| Market-version comparison | Which outcomes change between vSPD 5 and SPD v16 rules? | Supported comparison, bounded by data | Cross-version experiment and report crosswalk | Same eligible source population under explicit profiles |

“Can start now” means the current Python scenario API can express the primary
counterfactual. It does not remove the need to source data, predeclare metrics,
run controls, and build an evidence pack. “Mixed” means a useful screening
study can run now, but the full research question would add algebra.

## Near-term builds using the current formulation

### Historical stress-event atlas

Build a preregistered collection of unusual days: islanding, major branch or
generator outages, scarcity, high HVDC flow, reserve shortfall, negative price,
and daylight-saving transitions. For each event, compare the observed input
with a narrowly defined counterfactual such as restoring one asset's capacity.

The deliverable should contain:

- the source event and input hashes;
- the event-selection rule, including rejected candidates;
- baseline and counterfactual dispatch, reserve, violations, branch flow, and
  published prices;
- a causal boundary that distinguishes modelled effects from historical claims;
  and
- parity checks for the unchanged baseline before interpreting the scenario.

This is a strong first portfolio build because it exercises the qualified
single-period formulation without inventing inter-period physics.

### Demand, offer, and network sensitivity library

Turn the existing scalar override examples into reusable, hash-bound experiment
definitions. Useful experiments include demand multipliers, selected offer
price/capacity sweeps, generator withdrawals, and branch deratings. Each sweep
should include the original value as a control and should report regime changes
rather than fitting a single response through discontinuities.

The first implementation can remain outside the stable CLI while the scenario
schema is finalized. A production build should eventually add typed experiment
classes, deterministic scenario IDs, manifest-bound override records, and a
comparator that aligns all scenario outputs by the full case identity.

### Residential-PV paper replication

[Stage 13](../gate-13/README.md) is the most clearly specified planned study.
It will transform time-varying residential PV into auditable nodal demand
reductions and reproduce the source paper's scenario definitions and metrics.
Development must wait for the complete paper and supplements to pass the source
entry gate; generic demand scaling is not a substitute for replication.

## Inter-period model builds

Storage, flexible demand, hydro budgets, and unit commitment all require more
than solving several independent periods in one container. Their value comes
from equations that link decisions through time. They should therefore share a
versioned multi-period foundation with:

- an ordered trading-period domain that handles 46-, 48-, and 50-period days;
- explicit initial and terminal conditions;
- component-owned linking variables and constraints;
- deterministic period/scenario identities in every result;
- structural signatures that force a rebuild when topology or time domains
  change; and
- a pricing policy that states how discrete decisions are fixed before the
  RMIP and how intertemporal duals are interpreted.

Battery storage is the best first inter-period build. A minimal storage model
has an intuitive conservation equation and can be validated against a small
analytic example before adding reserve participation or degradation. Hydro and
unit commitment should follow only after the common time-coupling architecture
has demonstrated clean-build parity and order independence.

## Uncertainty and investment builds

Stochastic dispatch, robust security, and endogenous transmission investment
materially expand the decision problem. They should not be introduced as flags
on the historical compatibility formulation. Each needs a named research
profile and a declared interpretation of prices and welfare.

For renewable uncertainty, begin with an extensive-form model containing two
or three explicit scenarios and non-anticipativity only where justified. For
transmission investment, screen candidate capacities using existing audited
overrides before introducing binary build decisions, annualized costs, or
multi-year demand assumptions. The screening phase can eliminate weak projects
without increasing the trusted algebraic surface.

## Common build-and-gate pattern

Every new case study should use the following sequence.

1. **Question and boundary** — state the hypothesis, counterfactual, dates,
   population, formulation, metrics, and claims that the model cannot support.
2. **Source gate** — acquire and hash all input, assumptions, external data,
   papers, and reference outputs; record units, licences, and transformations.
3. **Analytic fixture** — construct the smallest case whose optimum, balances,
   active constraints, and expected price behavior can be checked independently.
4. **Probity TDD** — capture the missing behavior as a failing requirement test,
   implement it in a class-owned component, then retain red/green evidence.
5. **Structural validation** — compare variables, equations, coefficients,
   bounds, integrality, objective terms, and matrix hashes with the declared
   reference or independent derivation.
6. **Solve validation** — require optimal status, feasibility, objective and
   primal agreement, then evaluate duals and published prices using declared
   tolerances and analytical intervals.
7. **Historical pilot** — run one representative day plus a no-change control;
   investigate every material difference before expanding the sample.
8. **Population evidence** — select dates before seeing results, include odd and
   boundary cases, and preserve failures and exclusions in a discrepancy log.
9. **Reproducible release** — bind code, lock file, input, configuration,
   scenario, solver, environment, reports, and evidence by cryptographic hash.

## Choosing what to build next

A practical order is:

1. historical stress-event and sensitivity studies using existing overrides;
2. Stage 13 residential-PV replication once its source gate passes;
3. the common multi-period foundation and a minimal battery study;
4. hydro-budget and flexible-demand components;
5. unit commitment; and
6. stochastic or endogenous investment formulations.

This order produces useful research outputs early while increasing model
complexity only after each underlying validation layer has been exercised.
Use the [extension guide](../developer-guide/extending.md) for component and
formulation boundaries and the [validation guide](../validation/index.md) for
the evidence pack expected from each build.
