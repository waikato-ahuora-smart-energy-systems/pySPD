# External validation evidence

PySPD keeps its code, analytic fixtures, compact certificates, and evidence
manifests in Git. Large historical GDX inputs, raw CPLEX result trees, and
detailed per-case solver observations are immutable GitHub release assets. This
keeps an ordinary checkout small without weakening the evidence chain.

## Evidence release v1

The tracked
[`manifest-v1.json`](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/main/evidence/manifest-v1.json)
binds four archives by URL, SHA-256, byte size, file count, and uncompressed
size.

| Artifact | Contents | Compressed | Restored |
|---|---|---:|---:|
| `cplex-reference-v1` | Ten random CPLEX reference days | 105.8 MB | 680.9 MB |
| `cplex-consecutive-v1` | Five consecutive CPLEX days | 83.5 MB | 554.0 MB |
| `odd-day-reference-v1` | Twelve odd-day inputs and six 2019 result trees | 69.8 MB | 381.6 MB |
| `gate12-solver-paths-v1` | Detailed Gate 12 solver-path observations | 9.5 MB | 293.5 MB |

The release is
[`evidence-v1`](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/releases/tag/evidence-v1).
The manifest logical SHA-256 is
`e26a46494837dc1636df1570205b3ef985be3588edce8992df7f07a2768f5e6b`.

## Restore evidence

List the available artifacts:

```shell
uv run pyspd evidence list
```

Restore only the corpus needed by a study:

```shell
uv run pyspd evidence fetch odd-day-reference-v1 --destination .
```

For a private repository, use the existing Git credential helper without
placing a token in shell history:

```shell
uv run pyspd evidence fetch odd-day-reference-v1 --github-auth --destination .
```

The archive is cached under `PYSPD_EVIDENCE_CACHE`, when set, or the platform
cache directory. Downloads are written to a temporary file, checked against
both the declared hash and size, then atomically promoted. Extraction rejects
absolute paths, parent traversal, symbolic links, hard links, and special
files. Existing destination files must be byte-identical.

## Test boundary

An ordinary `uv run pytest -q` never initiates a download. Source-backed tests
call `require_external_evidence` and report an explicit skip containing the
artifact restoration command when data is absent. A skip confirms only that
the optional corpus is not installed; it is not a passing oracle result.

After restoring all four artifacts, run the external boundary tests and then
the wider suite:

```shell
uv run pytest tests/data tests/gate12 tests/studies -q
uv run pytest -q
```

## Rebuild and publication

`tools.build_evidence_archives` creates deterministic gzip/tar archives with
sorted paths, normalized metadata, and a zero gzip timestamp. The guarded
publisher creates a draft release, refuses to replace an existing asset, checks
the uploaded byte count, and publishes only after every expected asset exists.

Release v1 was independently downloaded through the authenticated API,
SHA-256 verified, restored into a clean temporary destination, and compared
byte-for-byte with all 412 source files. No mismatches were found.

The current release assets preserve the evidence content. A later Git-history
rewrite requires a separate recovery bundle and commit-provenance migration;
it must not be inferred from the externalization step alone.
