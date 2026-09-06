# Research-profile Probity TDD record

This working-tree record captures the behavioral red and green runs for the
historical stress-event atlas and multi-period battery research profile.

| Field | Value |
|---|---|
| Requirements | `REQ-STUDY-ATLAS`, `REQ-MULTIPERIOD-BATTERY` |
| Parent commit | `704afe4` |
| Package manager | `uv 0.11.29` |
| Python | `3.13.14` |
| Lock SHA-256 | `cc8553b5159a323585f30394f2605318caf6444119033087bd126e6a79bed39a` |
| Command | `uv run pytest tests/studies/test_stress_atlas.py tests/multiperiod/test_battery.py -q` |
| Red | [Two behavioral failures](logs/atlas-battery-red.log) |
| Green | [13 tests passed](logs/atlas-battery-green.log) |

The final test blobs are:

- `tests/studies/test_stress_atlas.py`:
  `6a667c6f13a7c3c342b0e85a483d86fbec85e2b9758cf8288da1fc06ac39eee1`;
- `tests/multiperiod/test_battery.py`:
  `90a660db0859a67e1f9338a972e6fcbe4c7216b85afc99d3a107f6fde170eaac`.

The formal TDD evidence JSON must be bound to the eventual implementation
commit SHA. It is intentionally not fabricated while these changes remain in
the working tree.
