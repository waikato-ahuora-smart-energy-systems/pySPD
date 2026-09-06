# Gate 11 Probity TDD evidence

Two red phases are retained:

1. the planned v16 compatibility, schema, preprocessing, formulation, pricing,
   reporting, and v5-non-regression contract failed collection before the
   implementation existed; and
2. the first real v16 oracle run exposed an omitted battery discrete variable,
   which received a focused failing regression before the overlay correction.

Green command:

```shell
uv run pytest tests/v16 tests/oracle/test_vspd_runner.py -q
```

The cumulative suite, ruff, and mypy results are bound in
`../qualification.json`.

