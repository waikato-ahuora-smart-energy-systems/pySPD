# Jupyter notebook examples

Learn PySPD with eight worked notebooks. The first six contain fictional data
and run with the published `pyspd==0.1.0` package. Each notebook includes all its
model-building code, plots, numerical checks, and suggestions for further
experiments. Start with notebook 01; every notebook also works independently.

| Example | Focus | Download |
|---|---|---|
| 01 · First dispatch | Two offers, energy balance, dispatch cost, and a price sensitivity check | {download}`Notebook <../examples/notebooks/01_first_dispatch.ipynb>` |
| 02 · Dispatch, flows, and prices | Congestion, nodal prices, and a simple congestion-rent calculation | {download}`Notebook <../examples/notebooks/02_dispatch_flows_and_prices.ipynb>` |
| 03 · Demand and offer sensitivity | Parameter sweeps and an unchanged baseline | {download}`Notebook <../examples/notebooks/03_demand_and_offer_sensitivity.ipynb>` |
| 04 · Outages and congestion | Generator withdrawal and circuit transfer restrictions | {download}`Notebook <../examples/notebooks/04_outages_and_congestion.ipynb>` |
| 05 · Reserve and scarcity | Native SCIP dispatch, HiGHS pricing, and explicit reserve shortfall | {download}`Notebook <../examples/notebooks/05_reserve_and_scarcity.ipynb>` |
| 06 · Battery storage | Efficiency, state of charge, and terminal energy across four hours | {download}`Notebook <../examples/notebooks/06_multiperiod_battery.ipynb>` |
| 07 · Entire NZ grid setup | Consume a whole-grid GDX, solve every case and period, and download the full results solution ZIP | {download}`Notebook <../examples/notebooks/07_entire_nz_grid.ipynb>` |
| 08 · Battery + PV at grid nodes | Set node IDs and capacities, then compare baseline and battery/PV whole-grid solutions | {download}`Notebook <../examples/notebooks/08_nodal_battery_and_pv.ipynb>` |

## Run a notebook

Save a notebook in a study directory. No repository checkout is needed:

```shell
uv venv --python 3.13
uv pip install --python .venv/bin/python "pyspd==0.1.0" "jupyterlab>=4,<5" "matplotlib>=3.10,<4" "pandas>=3,<4"
.venv/bin/jupyter lab
```

Open the notebook, select the environment's Python 3 kernel, and choose
**Restart Kernel and Run All Cells**. The examples target Python 3.13 and
macOS ARM64. SCIP and HiGHS install automatically with PySPD. The first six
need no external data or GAMS runtime.

The saved outputs are worked examples; rerun the cells to check your own
environment. At offer or network-capacity breakpoints, multiple marginal
prices can be valid. The notebooks explain where that matters and check
physical quantities before interpreting prices.

## Entire NZ grid setup

Notebook 07 consumes your compatible v5-style NZ grid GDX input and solves every
case and period it contains. Install `pyspd[gdx]==0.1.0`, set `INPUT_GDX`, and run
all cells. It discovers the bundled GDX reader runtime automatically; a separate
runtime can be specified with `GDX_RUNTIME_DIRECTORY`.

The notebook returns a downloadable `nz-grid-…-solution.zip` containing all twelve
CSV reports, their verified manifest, the run configuration, and the complete input
case inventory. No report rows are trimmed. This is a ZIP of PySPD's full report
solution, not a GDX output. Grid coverage comes from the supplied input.

With no input supplied it prints **NOT RUN** and produces no solution; saved
outputs do not claim an entire-grid solve. Full daily inputs can require substantial
time and memory. Review local paths and external data before sharing results.

See [inputs and GDX](user-guide/inputs-and-gdx.md) for input requirements and
[results and prices](user-guide/results.md) for interpreting the report bundle.

## Choose the right model

Notebook 08 extends the whole-grid workflow with a short `SITES` settings block
for node IDs, PV MW, battery MW, and battery MWh. It checks state of charge, losses,
power limits, and terminal energy, applies audited changes to demand at those nodes,
and runs a baseline and scenario across every case in the input. Both complete
solutions, comparison CSVs, schedules, and per-case asset effects are downloadable
in one ZIP. It accepts a custom PV and battery schedule CSV; its default profile is
illustrative. The schedule preview works without a GDX.

This is a simplified study of scheduled behind-the-meter effects. The battery
schedule is fixed, surplus PV is curtailed at zero net demand, and battery export
is rejected. The grid re-optimizes around those effects; the new assets do not bid
as generators or provide reserves. Use a complete daily input with 46, 48, or 50
half-hour trading periods.

Notebooks 01–04 use energy/network LPs with HiGHS to introduce dispatch and
price mechanics. Notebook 05 uses the full reserve solve policy. Notebook 06
uses the separate [battery research profile](case-studies/battery-storage.md).
These synthetic examples are learning tools and do not establish historical
parity or current market rules. For real input changes, continue with the
[audited scenario API](user-guide/audited-scenarios.md).
