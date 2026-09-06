# Command-line reference

Run these commands from the repository root after synchronizing the required
[dependency groups](../getting-started.md#1-prepare-the-environment).
Use `uv run pyspd --help` or add `--help` to any subcommand for its accepted
arguments. There are three top-level commands: `formulations`, `run`, and
`evidence`.

## `formulations`

List the formulation IDs registered in the production application:

```shell
uv run pyspd formulations
uv run pyspd formulations --json
```

The default output is one ID per line. `--json` returns an object with a
`formulations` array. The separate multi-period battery research profile is
not registered here.

## `run`

```shell
uv run pyspd run --config run.json
uv run pyspd run --config run.json --workers 3
```

| Argument | Required | Meaning |
|---|---|---|
| `--config PATH` | yes | JSON document accepted by `ApplicationConfiguration.from_json` |
| `--workers N` | no | Positive integer overriding `worker_count` for this invocation |

See [configuration fields](configuration.md) for the complete JSON contract.
The worker override changes the effective configuration hash. Paths inside
JSON resolve against the current working directory.

A successful run prints JSON with these keys:

| Key | Meaning |
|---|---|
| `state` | Final daily-run state; `complete` for a successful run |
| `output_directory` | Resolved report destination |
| `report_manifest_sha256` | Logical hash of the report manifest, including table hashes |

The CLI does not accept scenario overrides, checkpoint/resume options, a
canonical-feed directory, or arbitrary solver flags. Use the documented
[Python scenario API](../user-guide/audited-scenarios.md) for counterfactuals.

## `evidence list`

```shell
uv run pyspd evidence list
uv run pyspd evidence list --manifest evidence/manifest-v1.json
```

Prints the evidence manifest logical hash and artifact metadata as JSON.
Listing does not download archives.

## `evidence fetch`

```shell
uv run pyspd evidence fetch cplex-reference-v1 --destination .
uv run pyspd evidence fetch odd-day-reference-v1 --github-auth --destination .
```

Fetches an archive when absent from the cache, verifies it, then extracts it to
the destination. Existing destination files must be byte-identical. The result
JSON includes the archive path, destination, whether a download occurred,
extracted-file count, and verification status.

## `evidence verify`

```shell
uv run pyspd evidence verify cplex-reference-v1
```

Verifies a **cached archive's** hash and size. This command does not download a
missing archive, verify an extracted directory, or validate solver results.
Use `fetch` to restore an archive and `ReportBundle.read` to inspect a PySPD
report bundle.

## Evidence arguments

| Argument | Commands | Default / behavior |
|---|---|---|
| `ARTIFACT_ID` | `fetch`, `verify` | Required; copy an ID from `evidence list` |
| `--manifest PATH` | all evidence commands | `evidence/manifest-v1.json`, relative to the working directory |
| `--cache PATH` | `fetch`, `verify` | `PYSPD_EVIDENCE_CACHE` or the platform cache directory |
| `--github-auth` | `fetch`, `verify` | Read authentication from the configured Git credential helper |
| `--destination PATH` | `fetch` | Current working directory |

The [external evidence guide](../validation/external-evidence.md) describes
archive contents and the test boundary.

## Exit status and logs

Successful commands return `0`. Argument errors and handled configuration,
input, evidence, and filesystem errors return `2`. Other runtime failures can
produce a traceback and another nonzero exit status; automation should treat
any nonzero status as a failed command.

Retain both output streams for a study. In a shell supporting `pipefail`:

```shell
set -o pipefail
uv run pyspd run --config run.json 2>&1 | tee run.log
```

Check the process exit status and the output bundle rather than treating the
presence of a log or some CSV files as proof of completion.
