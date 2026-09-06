# PySPD notebook examples

Eight worked notebooks for **PySPD 0.1.0**. Six use fictional inputs, plots,
interpretation, and numerical checks; two run studies on your NZ grid GDX.
Each notebook includes its own code and runs independently against the installed package.

| Notebook | What you learn | Inputs |
|---|---|---|
| [01 · First dispatch](01_first_dispatch.ipynb) | Merit order, balance, cost, and a finite-difference price check | Synthetic |
| [02 · Dispatch, flows, and prices](02_dispatch_flows_and_prices.ipynb) | Nodal prices, congestion, and an illustrative congestion rent | Synthetic |
| [03 · Demand and offer sensitivity](03_demand_and_offer_sensitivity.ipynb) | Fresh cases, parameter sweeps, and baseline comparisons | Synthetic |
| [04 · Outages and congestion](04_outages_and_congestion.ipynb) | Generator withdrawal, line derating, and incremental cost | Synthetic |
| [05 · Reserve and scarcity](05_reserve_and_scarcity.ipynb) | SCIP dispatch, HiGHS pricing, FIR/SIR, and reserve shortfall | Synthetic |
| [06 · Battery storage](06_multiperiod_battery.ipynb) | Time coupling, efficiency, power/energy limits, and terminal state | Synthetic |
| [07 · Entire NZ grid setup](07_entire_nz_grid.ipynb) | Consume a whole-grid GDX, solve every case and period, and return the full results solution ZIP | Your NZ grid GDX |
| [08 · Battery + PV at grid nodes](08_nodal_battery_and_pv.ipynb) | Change node/capacity rows, apply a feasible battery and PV schedule, and compare two full-grid solutions | Your NZ grid GDX |

## Start without a repository checkout

Download any notebook from the RTD notebook page, or download its raw `.ipynb`
file from GitHub. Save it in an empty study directory, then run:

```shell
uv venv --python 3.13
uv pip install --python .venv/bin/python "pyspd==0.1.0" "jupyterlab>=4,<5" "matplotlib>=3.10,<4" "pandas>=3,<4"
.venv/bin/jupyter lab
```

Open the downloaded notebook with the environment's Python 3 kernel and choose
**Restart Kernel and Run All Cells**. SCIP and HiGHS install with PySPD. The first
six notebooks require no GAMS runtime or external datasets. Notebook 01 takes
about ten minutes to work through; its solves take seconds.

For **Entire NZ grid setup**, install `"pyspd[gdx]==0.1.0"` in the same environment,
set `INPUT_GDX`, and run all cells. The notebook discovers the bundled GDX reader
runtime automatically; `GDX_RUNTIME_DIRECTORY` supports a separate installation.
It solves all cases and periods and returns one downloadable solution ZIP with
all twelve CSV reports, their verified manifest, the run configuration, and input
case inventory. The ZIP preserves every report row; it is not a GDX output.
With no input, it prints **NOT RUN** and produces no solution. Saved outputs only
check that unconfigured path. Review local paths and external results before sharing.

For **Battery + PV at grid nodes**, change the input path and `SITES` rows to set
node IDs, PV MW, battery MW, and battery MWh. The notebook checks a fixed battery
schedule, applies audited net-demand changes, and solves all cases for both the
baseline and scenario. One ZIP contains both full solutions, comparisons, the
schedule, and per-node effects. You can supply your own PV and battery profile CSV.
The battery schedule is prescribed, not optimized; surplus PV is curtailed and
battery export is rejected. New assets are represented through demand rather than
separate energy or reserve offers. A schedule preview runs without external data.

The checked examples target Python 3.13 on macOS ARM64. Notebooks 01–04 use
small energy/network LPs and direct HiGHS pricing. Notebook 05 uses the
SCIP-to-HiGHS reserve solve policy. Notebook 06 uses the separate analytic
battery profile. The examples do not establish historical parity or represent
current market settings. A zero line limit in notebook 04 restricts transfer;
it does not remove the circuit from the electrical topology.

## Reproduce notebook validation

From a checkout, create a separate environment so PySPD imports come from PyPI:

```shell
uv venv --python 3.13 .notebook-venv
uv pip install --python .notebook-venv/bin/python -r examples/notebooks/requirements.txt
.notebook-venv/bin/python tools/run_notebook_examples.py
```

The runner uses a fresh kernel and temporary working directory for each notebook,
rejects imports from a source checkout, and fails on cell errors. It writes
executed notebooks and an environment/execution report under
`dist/notebook-validation/`. The optional GDX run stays disabled during this
check. Add `--write-executed` to refresh the examples' saved outputs, or
`--only '05_*.ipynb'` to validate one example. No package publication is needed
to add or download these notebooks.
