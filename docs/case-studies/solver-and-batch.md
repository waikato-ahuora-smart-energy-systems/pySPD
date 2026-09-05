# Solver and batch comparisons

## Compare fixed-RMIP backends

Keep input, cases, formulation and all numerical settings constant. Change only
the solver profile and output directory.

=== "SCIP → HiGHS"

    ```json
    {
      "solver_profile": "scip-mip-fixed-highs-rmip",
      "output_directory": "/results/20230927/highs"
    }
    ```

=== "SCIP → CLP"

    ```json
    {
      "solver_profile": "scip-mip-fixed-clp-rmip",
      "output_directory": "/results/20230927/clp"
    }
    ```

Install CLP with:

```shell
uv sync --frozen --group clp
```

Compare in this order:

1. requested/completed case identities;
2. solver status and violation quantities;
3. fixed discrete/SOS state;
4. objective and primal physics;
5. raw duals; and
6. repaired, node, and published prices with interval containment.

The CLP path is useful independent evidence, but HiGHS remains the normal
qualified backend. A faster path is not automatically a more faithful one.

## Compare MIP backends

CBC profiles are experimental alternatives:

```text
cbc-mip-fixed-highs-rmip
cbc-mip-fixed-clp-rmip
```

Install CBC with `uv sync --frozen --group cbc`. Compare the chosen discrete
support as well as objective and final prices. Different MIP supports can be
economically equivalent but produce different fixed-RMIP dual faces.

## Performance trial

Warm caches once, then alternate execution order to reduce order bias. Record:

- total wall time;
- solver time and solve-call count;
- preparation, report, and write time if instrumented;
- worker count and per-solver thread count;
- peak resident memory; and
- complete result/parity checks.

Do not compare a three-worker run with a ten-worker run on different case
populations. PySPD's retained evidence found ten workers beneficial for a full
263-case day but not for a 12-case workload.

## Multi-day batch

Use one immutable config per input date. A simple driver can run them
sequentially and fail on the first error:

```python
import subprocess
from pathlib import Path

for configuration in sorted(Path("studies/configs").glob("*.json")):
    subprocess.run(
        ["uv", "run", "pyspd", "run", "--config", str(configuration)],
        check=True,
    )
```

For outer parallelism, bound the number of concurrent days and set each inner
configuration's `worker_count` so total process count and memory remain safe.
Avoid multiplying ten day workers by ten case workers accidentally.

## Sampling unusual days

Predeclare selection rather than choosing favorable outcomes. Useful strata
include:

- 46- and 50-period daylight-saving days;
- high and negative price days;
- generation or reserve shortfall;
- network islands and major outages;
- high HVDC transfer/loss segments;
- reserve-sharing or round-power boundaries; and
- dates around formulation/data-schema changes.

Hash the complete candidate inventory and the deterministic selection
algorithm. Retain excluded days and reasons in the sampling record.

## Vectorized multi-period models

PySPD has experimentally assembled multiple periods into one Pyomo model. The
two-period trial matched objective and primal values after period indexing was
repaired, but was slower and the algebra was almost entirely separable. Dynamic
independent-case multiprocessing is therefore the production strategy.

Reconsider vectorization only when a study adds genuine inter-period equations,
such as storage state, unit commitment, or energy budgets. Such a formulation
is a new versioned model, not a transparent performance option.
