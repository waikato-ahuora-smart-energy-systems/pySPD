# Results and prices

Each run writes `manifest.json` plus twelve CSV files. The manifest records the
formulation, provenance, field definitions and units, row counts, individual
file hashes, and one logical bundle hash.

## Begin with summary and audit

Check `summary.csv` before interpreting market outcomes:

- `status_code` must be 1 for every requested case;
- violation quantities and `violation_cost_nzd` show whether scarcity or a
  relaxation affected the solution;
- `system_ofv_nzd`, cost, and benefit support objective comparisons; and
- case IDs and datetimes confirm the intended population ran.

Then inspect `audit.csv`. It records bounded solve-loop transitions, override
application, node transfers, acceptance, and price publication in sequence.

## Price surfaces

PySPD distinguishes four concepts:

1. `bus.raw_price_nzd_per_mwh` is the fixed-RMIP balance dual.
2. `bus.repaired_price_nzd_per_mwh` applies governed disconnected/dead-bus and
   zero-flow price rules.
3. `node.price_nzd_per_mwh` applies source node-to-bus allocation factors.
4. `published_price.price_nzd_per_mwh` applies publication-duration weighting
   and the configured decimal boundary.

Do not compare a raw bus marginal with an Authority published node price.
Match the table, identity, units, and publication aggregation first.

## Analytical price intervals

`price_interval` is empty for a unique or currently uncertified scalar. Where
present, it is a closed JSON interval such as:

```text
[199.92455,201.58105]
```

It represents independently derived valid one-sided marginal values at a
non-differentiable or degenerate point. The scalar price remains the endpoint
selected by the governed convention. A benchmark value anywhere inside the
interval is accepted; the interval is not permission to accept an arbitrary
price outside it.

## Large report surfaces

`constraint.csv` can dominate time and storage. A qualified 48-period legacy
day produced 1,504,321 constraint rows and roughly 208 MiB for that table
alone. For exploratory analysis, read only required columns and filter by case
or constraint family with a streaming or columnar tool. Do not delete tables
from a qualification bundle after its manifest has been written—the file hash
check will correctly fail.

## Reading a bundle in Python

```python
from pathlib import Path

from pyspd.reporting import ReportBundle

bundle = ReportBundle.read(Path("results/base"))
summary = bundle.tables["summary"]
published = bundle.tables["published_price"]

print(len(summary.rows), len(published.rows))
for row in published.rows:
    if row["product"] == "energy" and row["location"] == "WPT1101":
        print(row)
```

`ReportBundle.read` verifies the manifest logical hash, every CSV hash, schema,
and row count before returning data.

See the complete field inventory in the [report reference](../reference/reports.md).
