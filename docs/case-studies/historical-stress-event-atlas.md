# Historical stress-event atlas

The first atlas is a reproducible screen of every result-backed day in PySPD's
retained CPLEX corpora. It selects the population before classification, checks
the input and result-tree hashes, extracts comparable daily metrics, and assigns
threshold-based stress categories.

This is an evidence inventory, not a causal study. A category identifies a day
worth investigating; it does not prove that an outage, constraint, offer, or
policy setting caused the observed outcome.

## Registered population

The immutable [preregistration](evidence/historical-stress-event-atlas-v1/preregistration.json)
includes all unique result-backed days from:

- the ten-day random CPLEX reference corpus;
- the five-day consecutive CPLEX confidence corpus; and
- the six CPLEX-backed 2019 days in the odd-day corpus.

The resulting 21 dates comprise 11 days from 2019 and 10 from 2023. The
result-free 2022 odd-day inputs are correctly excluded because this version of
the atlas screens archived CPLEX outputs.

## Registered signals

| Category | Rule |
|---|---|
| Long DST day | 50 distinct trading periods |
| Short DST day | 46 distinct trading periods |
| High energy price | maximum node price at least NZD 1,000/MWh |
| Negative energy price | minimum node price below NZD 0/MWh |
| High reserve price | maximum FIR or SIR price at least NZD 300/MW |
| Network stress | maximum absolute branch flow/capacity at least 98% |
| Violation | maximum reported violation exceeds `1e-6` MW or violation cost is positive |
| Solve failure | any summary solve status is not 1 |

The thresholds are screening parameters and are part of the atlas hash. Change
them only by creating a new preregistration and study ID.

## Results

The scan found:

- one 50-period and two 46-period days;
- 14 days with a reported violation quantity or cost;
- one day above the energy-price threshold;
- two days above the reserve-price threshold;
- no negative-price day in this retained population;
- no day reaching 98% maximum branch utilization; and
- no unsuccessful archived CPLEX summary row.

The most useful first diagnostic candidates are:

| Date | Signal | Measured boundary |
|---|---|---:|
| 2019-10-21 | largest violation quantity | 11.8 MW; NZD 10.71 million violation cost |
| 2023-08-02 | largest reserve-price signal | NZD 1,360.001/MW |
| 2019-06-19 | high energy and reserve prices | NZD 1,024.226/MWh and NZD 313.859/MW |
| 2023-09-25 | largest total violation cost in this atlas | NZD 34.433 million |
| 2019-04-07 | fall-back time boundary | 50 trading periods |
| 2019-09-29 and 2023-09-24 | spring-forward boundaries | 46 trading periods each |

Use the retained [human-readable atlas](evidence/historical-stress-event-atlas-v1/README.md),
[complete JSON](evidence/historical-stress-event-atlas-v1/atlas.json), or
[flat CSV](evidence/historical-stress-event-atlas-v1/events.csv). The logical
atlas SHA-256 is
`756dd640b31bfc57e94044d32e94ca798028f46d6bd9220b2dafbef5b9eed74a`.

## Rebuild the atlas

From the repository root:

```shell
uv run python -m tools.build_stress_event_atlas
```

The builder fails if a source hash, result-tree hash, summary row count, DST
period count, or required report table differs. Output ordering and numeric
serialization are deterministic.

## Turn a signal into a causal case study

For one selected date:

1. inspect the case-level rows and identify the periods contributing to the
   registered daily extreme;
2. use the GDX input to identify active assets, constraints, risks, scarcity
   settings, and offer conditions in those periods;
3. reproduce the unmodified case with PySPD and pass the applicable CPLEX
   comparator before applying an override;
4. preregister one physically meaningful counterfactual, such as restoring a
   branch capacity or withdrawing one generator;
5. run a no-change control and the counterfactual through distinct output
   directories; and
6. compare violations and primal physics before interpreting prices, rentals,
   reserve, or welfare.

The first recommended causal follow-up is 2019-10-21 because its 11.8 MW
violation is materially larger than the other 2019 events. The 2023-08-02
reserve-price event is the best independent reserve-policy follow-up.

## Interpretation boundary

`total_system_cost` and `total_violation_cost` are sums of the archived summary
rows. v5 daily sources can contain several pricing cases per trading period, so
these totals are screening measures, not published daily settlement totals.
Node and reserve extremes come from the retained CPLEX result surfaces. Branch
utilization uses `abs(flow) / abs(capacity)` and ignores zero-capacity rows.

Dates absent from the retained corpus were not tested and cannot be called
non-stress days. Outages and islanding are not inferred from output magnitude;
they need topology-aware input diagnostics in the causal follow-up.

```{toctree}
:hidden:

evidence/historical-stress-event-atlas-v1/README
```
