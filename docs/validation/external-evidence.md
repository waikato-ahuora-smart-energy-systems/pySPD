# External validation evidence

PySPD keeps its code, analytic fixtures, compact certificates, and evidence
manifests in Git. Large historical GDX inputs, raw CPLEX result trees, and
detailed per-case solver observations are immutable GitHub release assets. This
keeps an ordinary checkout small without weakening the evidence chain.

## Evidence release v1

The tracked
[`manifest-v1.json`](https://github.com/waikato-ahuora-smart-energy-systems/pySPD/blob/main/evidence/manifest-v1.json)
binds archives by URL, SHA-256, byte size, file count, and uncompressed size.
These three contain the historical inputs and reference results used in studies:

| Artifact | Contents | Compressed | Restored |
|---|---|---:|---:|
| `cplex-reference-v1` | Ten random CPLEX reference days | 105.8 MB | 680.9 MB |
| `cplex-consecutive-v1` | Five consecutive CPLEX days | 83.5 MB | 554.0 MB |
| `odd-day-reference-v1` | Twelve odd-day inputs and six 2019 result trees | 69.8 MB | 381.6 MB |

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

To recheck a downloaded archive without extracting it again:

```shell
uv run pyspd evidence verify odd-day-reference-v1
```

`verify` checks the cached archive only and fails when it is absent. It does not
check extracted files or solver results. See the [CLI reference](../reference/cli.md)
for cache and manifest arguments.

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

## Using restored results

Keep the original files and hashes with your study. Archive verification
establishes file integrity; it does not establish that a model reproduces the
reference results. Compare matching case identities, units, report fields, and
publication periods using [interpreting parity](interpreting-parity.md).
