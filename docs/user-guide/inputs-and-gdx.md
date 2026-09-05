# Inputs and GDX

## What the application reads

The stable application reads one daily GDX into immutable `RawSymbols` using
GAMS Transfer. It then applies the selected legacy adapter if required and
validates the complete symbol inventory against a versioned `SymbolCatalog`.
Missing symbols, wrong dimensions, incompatible domains, and unsupported input
schemas fail before model assembly.

GDX conversion needs three things:

1. the `gdx`/GAMSPy Python dependency;
2. an installed GAMS runtime containing GAMS Transfer support; and
3. the correct GAMS system-directory path.

```shell
uv sync --frozen --group gdx
```

A GAMSPy license is helpful for GAMSPy models and data access, but reading a GDX
does not make a GAMSPy-only license equivalent to CPLEX entitlement for an
existing GAMS program.

## Inventory cases before a study

Use the same selector as the application:

```python
from pathlib import Path

from pyspd.data import GdxAdapter, LegacyV3InputAdapter
from pyspd.orchestration import DailyCaseSelector

input_path = Path("/data/Pricing_20230927.gdx")
gams_directory = Path("/Library/Frameworks/GAMS.framework/Resources")

symbols = GdxAdapter.read(input_path, system_directory=gams_directory)
# Uncomment for an input declared as vspd-v3-final-pricing:
# symbols = LegacyV3InputAdapter().normalize(symbols)

for case in DailyCaseSelector().select(symbols):
    print(
        case.ordinal,
        case.case_id,
        case.date_time,
        case.trading_period,
        case.schedule_type.value,
        case.publication_seconds,
    )
```

Save this inventory with formal study evidence. It distinguishes multiple
pricing cases within one trading period and makes daylight-saving populations
visible.

## Convert to a canonical feed

For data inspection and GAMS-free downstream preprocessing, write Arrow-backed
canonical tables:

```python
from pathlib import Path

from pyspd.data import GdxAdapter

feed = GdxAdapter.write_feed(
    Path("/data/Pricing_20230927.gdx"),
    Path("/data/canonical/20230927"),
    system_directory=Path("/Library/Frameworks/GAMS.framework/Resources"),
)
print(feed.logical_sha256)
```

The canonical feed preserves symbol metadata, UEL ordering and GAMS special
values while storing records in a portable columnar form. It is useful for
audits and tooling, but the current stable `pyspd run` command still takes the
source GDX rather than a canonical-feed directory.

## Data handling rules

- Never infer input schema from date or filename.
- Retain the original GDX bytes and hash.
- Do not convert `EPS`, `NA`, `UNDEF`, or infinities silently to ordinary zero.
- Keep case, datetime, and trading-period identity together.
- Record any source transformation as a new artifact with before/after hashes.
- Do not publish licensed or restricted input data merely because a derived
  model run is shareable.

## Adding a new input schema

A new schema needs an explicit adapter and catalog, fixture/corpus inventory,
special-value tests, semantic preprocessing comparison, and an ADR. Best-effort
field matching is intentionally not supported.
