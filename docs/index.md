# PySPD Guide

PySPD is a Python implementation of New Zealand's Scheduling, Pricing, and
Dispatch model. It is built for researchers and analysts who need reproducible
market studies, transparent dispatch and pricing calculations, and comparisons
with historical vSPD results.

A run reads a declared GDX input, assembles a class-based Pyomo formulation,
solves dispatch with SCIP, and calculates fixed-discrete prices with HiGHS.
It writes twelve CSV tables and a manifest recording the input, configuration,
solver, and report hashes.

## Start Here

I want to run a case
: Start with [getting started](getting-started.md), then use
  [running PySPD](user-guide/running.md) to select cases or run a complete day.

I need to understand the results
: Read [results and prices](user-guide/results.md) for dispatch, raw and repaired
  prices, node allocation, publication weighting, and output verification.

I am building a market study
: Start with [choosing a case study](case-studies/index.md), then use the
  [audited scenario API](user-guide/audited-scenarios.md) for counterfactual inputs.

I want to compare historical results
: Use the [validation workflow](validation/index.md) and
  [interpreting parity](validation/interpreting-parity.md) to compare matching
  populations, report fields, numerical tolerances, and analytical intervals.

I need a command or field definition
: Look up the [CLI](reference/cli.md), [configuration fields](reference/configuration.md),
  [report tables](reference/reports.md), or [glossary](reference/glossary.md).

## What PySPD Covers

- v5-style pricing GDX and legacy v3 final-pricing inputs;
- energy dispatch, AC/HVDC networks, reserve, and version-specific formulations;
- SCIP dispatch followed by fixed-discrete HiGHS pricing;
- independent validation and deterministic report bundles;
- parallel execution of independent pricing cases;
- audited demand, offer, reserve, and network counterfactuals through Python; and
- a separate analytic multi-period battery research profile.

The qualified production environment is macOS ARM64 with Python 3.13. GDX
access requires a local GAMS runtime. The production formulations are
`vspd-v5.0.6-reserve` and `spd-v16.0-reserve`; the
[battery profile](case-studies/battery-storage.md) has a separate Python entry
point and is not registered in `pyspd run`.

Validation applies to specific inputs and output surfaces. Complete historical
parity is not established; read [current limitations](reference/limitations.md)
before extending a comparison claim to another date, platform, or formulation.

PySPD is licensed under the {download}`Apache License 2.0 <../LICENSE>`.
Third-party dependencies, external input data, and solver runtimes retain
their own terms.

```{toctree}
:maxdepth: 2
:caption: Documentation

getting-started
user-guide/index
case-studies/index
validation/index
reference/index
troubleshooting
```
