# External validation evidence

Large GDX inputs, raw CPLEX result trees, and detailed solver-path observations
are immutable release assets rather than Git blobs. The tracked
`manifest-v1.json` binds each archive by SHA-256, byte size, file count, and
uncompressed size.

List the available archives:

```shell
uv run pyspd evidence list
```

Restore one corpus into the repository paths expected by oracle tests:

```shell
uv run pyspd evidence fetch cplex-reference-v1 --destination .
```

For a private GitHub repository, opt in to the configured Git credential without
placing a token in the command line:

```shell
uv run pyspd evidence fetch cplex-reference-v1 --github-auth --destination .
```

The downloader writes the archive to `PYSPD_EVIDENCE_CACHE` or the platform
cache directory, verifies it before extraction, rejects links and paths outside
the destination, and refuses to replace differing local files. A repeated
fetch is idempotent.

Normal unit and structural tests must not download these archives. Tests that
need them are explicitly marked `oracle`; a clean CI checkout can run the
ordinary suite without the external corpus.

The release assets are supporting evidence, not package runtime dependencies.
Their original source and result-tree hashes remain in the restored corpus
manifests.

The same release also contains the complete pre-cleanup Git history as
`pyspd-pre-slim-history-v1.bundle`. Its hash, byte count, original head, and
rewritten equivalent are recorded in `history-manifest-v1.json`. Restore that
history into an isolated clone with:

```shell
git clone pyspd-pre-slim-history-v1.bundle pyspd-pre-slim-history
```
