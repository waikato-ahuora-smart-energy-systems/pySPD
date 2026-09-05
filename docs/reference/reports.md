# Report tables

All CSV fields are strings on disk. Numeric values use up to 17 significant
digits unless a governed publication rounding boundary applies. Empty strings
represent an inapplicable optional value, not numerical zero.

## `summary.csv`

One row per case. Contains solve status; objective, cost, benefit and violation
cost; and deficit/surplus totals for generation, reserve, branch flow, ramp
rate, branch constraints, and market-node constraints.

Primary identity: `case_id`, `date_time`.

## `island.csv`

One row per case, island and reserve class. Contains reserve price/interval,
generation, fixed and bid load, AC/HVDC losses and flow, reference price,
reserve requirement/clearing/sharing/receipt, and effective CE/ECE quantities.

Primary identity: `case_id`, `date_time`, `island`, `reserve_class`.

## `bus.csv`

Contains raw and repaired bus prices, analytical interval, disconnected/invalid
flags, and generation/load/deficit/surplus quantities.

Primary identity: `case_id`, `date_time`, `bus`.

## `node.csv`

Contains allocated node price and interval, dead-node status and price source,
plus generation/load/deficit/surplus quantities.

Primary identity: `case_id`, `date_time`, `node`.

## `offer.csv`

Contains offer/trader identity, energy generation, FIR and SIR clearing.

Primary identity: `case_id`, `date_time`, `offer`.

## `bid.csv`

Contains bid/trader identity, cleared purchase and total bid quantity.

Primary identity: `case_id`, `date_time`, `bid`.

## `reserve.csv`

Contains island/reserve-class price and analytical interval, required reserve,
and violation quantity.

Primary identity: `case_id`, `date_time`, `island`, `reserve_class`.

## `risk.csv`

Contains island, reserve class, risk class/type/setter; covered energy, reserve
and frequency-keeper quantities; subtractors; reserve, shortfall and deficit;
and reserve/risk prices.

The exact identity includes all descriptive risk columns. Do not key only on
the human-readable setter label.

## `branch.csv`

Contains flow, endpoints, capacity, dynamic/fixed losses, both endpoint prices
and intervals, branch price and rentals.

Primary identity: `case_id`, `date_time`, `branch`.

## `constraint.csv`

Contains the canonical model constraint name, component index, body, lower and
upper bounds, and dual price. It can contain more than a million rows per day.

Primary identity: `case_id`, `date_time`, `constraint`, `index`.

## `published_price.csv`

Contains trading period, location, product (`energy`, `FIR`, or `SIR`), rounded
price, analytical interval, publication seconds and representative datetime.

Primary identity: `trading_period`, `location`, `product`.

## `audit.csv`

Contains ordered state-machine events with case, solve-loop number and canonical
JSON details. Events include override, solve, shortfall, transfer, acceptance,
and publication transitions.

Primary identity: sequence within a run; repeated case labels are allowed when
their complete period identities differ.

## `manifest.json`

The manifest contains:

- schema version and formulation;
- field names, units and row counts for every table;
- SHA-256 for every CSV;
- source, configuration, dependency, package, solver and environment
  provenance; and
- one logical SHA-256 over the manifest payload.

Always use `ReportBundle.read` when consuming a formal evidence bundle; it
verifies hashes and schemas before exposing rows.
