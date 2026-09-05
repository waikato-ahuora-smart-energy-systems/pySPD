# Audited scenario API

The stable CLI replays data already present in a GDX. Counterfactual changes
currently use the lower-level Python API so every raw-symbol mutation has an
`OverrideAudit`. This is appropriate for controlled studies, but the scenario
definition must be retained and hashed separately because overrides are not yet
fields in `ApplicationConfiguration`.

## Supported override families

| Family | Typical use |
|---|---|
| `DEMAND` | Scale, increment, or replace node/island/system demand |
| `OFFER_PARAMETER` | Ramps, initial state, dispatchability, reserve factors |
| `ENERGY_OFFER` | Energy tranche quantity or price |
| `RESERVE_OFFER` | FIR/SIR PLRO/TWRO/ILRO tranche quantity or price |
| `BID_PARAMETER`, `ENERGY_BID` | Dispatchable-demand assumptions |
| `BRANCH_PARAMETER` | Directional capacity or branch input parameter |
| `BRANCH_CONSTRAINT_RHS`, `BRANCH_CONSTRAINT_FACTOR` | Security constraint studies |
| `MARKET_NODE_CONSTRAINT_RHS`, `MARKET_NODE_CONSTRAINT_FACTOR` | Market-node constraint studies |

Scopes are applied in fixed precedence: all-time, trading period, datetime,
then case ID. Later, narrower instructions therefore supersede broader ones.

## End-to-end pattern

The following function deliberately mirrors the application data boundary. It
validates the GDX before applying overrides, prepares each selected case, runs
the normal solve loop, and writes the ordinary report bundle.

```python
from collections.abc import Iterable
from pathlib import Path

from pyspd.application import ApplicationConfiguration, PyspdApplication
from pyspd.data import (
    LEGACY_V3_INPUT_SCHEMA,
    GdxAdapter,
    LegacyV3InputAdapter,
    SymbolCatalog,
)
from pyspd.orchestration import (
    DailyCaseDataIndex,
    DailyCasePreparer,
    DailyCaseSelector,
    DailyRunner,
    OverrideApplier,
    OverrideInstruction,
)
from pyspd.reserve import RESERVE_FORMULATION_ID
from pyspd.v16 import SPD16_FORMULATION_ID
from pyspd.v16.preprocess import SPD16_SOURCE_PROFILE_ID


def run_scenario(
    configuration: ApplicationConfiguration,
    instructions: Iterable[OverrideInstruction],
) -> str:
    app = PyspdApplication()
    symbols = GdxAdapter.read(
        configuration.input_path,
        system_directory=configuration.gams_system_directory,
    )
    if configuration.input_schema == LEGACY_V3_INPUT_SCHEMA:
        symbols = LegacyV3InputAdapter().normalize(symbols)

    catalog = (
        SymbolCatalog.spd_v16()
        if configuration.formulation_id == SPD16_FORMULATION_ID
        else SymbolCatalog.vspd_v5()
    )
    catalog.validate(symbols)
    selected = DailyCaseSelector().select(
        symbols,
        case_ids=configuration.case_ids,
    )
    index = DailyCaseDataIndex(
        symbols,
        case_ids=tuple(case.case_id for case in selected),
    )
    source_profile = (
        SPD16_SOURCE_PROFILE_ID
        if configuration.formulation_id == SPD16_FORMULATION_ID
        else "vspd-v5.0.6"
    )

    prepared = []
    for case in selected:
        source_case = index.case_data(case, formulation_id=source_profile)
        changed_case, audit = OverrideApplier().apply(
            source_case,
            tuple(instructions),
        )
        prepared.append(
            DailyCasePreparer().prepare(
                changed_case,
                case,
                daily_mode=True,
                override_audit=audit,
                formulation_id=configuration.formulation_id,
            )
        )

    result = DailyRunner(
        app.case_executor(configuration),
        postprocessor=app.price_postprocessor(configuration),
    ).run(app.daily_configuration(configuration), tuple(prepared))
    manifest = app.render_report_bundle(configuration, result).write(
        configuration.output_directory
    )
    return manifest.logical_sha256
```

`RESERVE_FORMULATION_ID` is shown in the imports to make the supported base
profile discoverable; the function itself respects the formulation named by
the configuration.

!!! warning "Scenario provenance"

    Save instructions as canonical JSON, hash that file, and include its hash
    beside the output manifest. `OverrideAudit` binds before/after symbol hashes
    into run events, but the stable application configuration does not yet bind
    the human-readable scenario definition.

## Scenario definition convention

A compact external record can look like:

```json
{
  "scenario_id": "ni-conforming-demand-plus-5pct-tp18",
  "baseline_input_sha256": "...",
  "instructions": [
    {
      "family": "demand",
      "scope": "trading_period",
      "selector": "TP18",
      "target": ["ISLAND", "NI", "CONFORMING", "SCALE"],
      "value": 1.05
    }
  ]
}
```

Convert each record explicitly to `OverrideInstruction`; do not feed arbitrary
JSON directly to constructors without schema and enum validation.

## Parallel counterfactuals

The lower-level pattern above is serial. The production worker path currently
reconstructs cases from the unmodified GDX, so it must not be used with an
out-of-band override list. For a large parallel study, either:

1. materialize a new, independently hash-bound GDX and use normal `pyspd run`;
2. run independent scenario/case jobs in an outer bounded process pool; or
3. extend `ApplicationConfiguration` with a governed, hash-bound scenario
   schema before passing overrides into production workers.

Option 3 is the preferred future application feature because it retains the
same dynamic scheduling and manifest contract.
