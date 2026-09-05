# Baseline and subset studies

## Complete historical replay

Use the unmodified source GDX, empty `case_ids`, qualified solver profile, and a
new output directory. This is the baseline for every counterfactual using that
day.

```json
{
  "formulation_id": "vspd-v5.0.6-reserve",
  "input_path": "/data/Pricing_20230927.gdx",
  "output_directory": "/results/20230927/base",
  "source_sha256": "...",
  "gams_system_directory": "/Library/Frameworks/GAMS.framework/Resources",
  "solver_profile": "scip-mip-fixed-highs-rmip",
  "input_schema": "vspd-v5.0.6",
  "case_ids": [],
  "worker_count": 10
}
```

Run:

```shell
uv run pyspd run --config studies/20230927-base.json
```

Check that the summary has the expected case count and that the set of trading
periods is correct. New Zealand daylight-saving transition days may have 46 or
50 trading periods rather than 48.

## Fast single-case diagnosis

Copy one exact case ID into `case_ids`, choose one worker, and use a dedicated
directory. This retains every model and report feature but avoids solving the
rest of the day.

Use it to:

- inspect a binding branch or market-node constraint;
- diagnose a risk setter;
- reproduce a shortfall solve loop;
- test a scenario instruction; or
- compare HiGHS and CLP pricing for the same fixed MIP state.

## Publication-aware prefix

When a trading period has multiple cases, a one-case solve may not reproduce
the official publication. Select the complete source-ordered group whose
`publication_seconds` contribute to that trading period. If earlier cases also
affect a rolling publication, include the required prefix.

The safest workflow is:

1. run the complete day once;
2. filter `published_price.csv` to the target period;
3. inspect `audit.csv` and source publication weights; and
4. shrink to a prefix only after proving the reduced population reconstructs
   the same publication.

## Paired baseline/scenario outputs

Never overwrite the baseline. A simple study tree is:

```text
studies/20230927/
  input.sha256
  base.json
  demand-plus-5pct.json
results/20230927/
  base/
  demand-plus-5pct/
```

Compare row identities before value differences. If a scenario intentionally
changes a domain—for example, by adding a new offer—record the expected identity
change separately from numerical deltas.
