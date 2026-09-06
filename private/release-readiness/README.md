# Package release preparation

This is the historical preparation record. The later user-directed publication
is documented in [PyPI 0.1.0 publication](pypi-publication.md).

The current `0.1.0` candidate passes the technical checks below. Public
distribution remains **held**: third-party redistribution decisions in the
licence register are still pending. The project licence is now Apache 2.0, as
explicitly requested for the project; see [LICENSE](../../LICENSE). Nothing has been
published or tagged.

## Candidate and evidence

Use only the artifacts in [`dist/candidate/`](../../dist/candidate/). Older
artifacts directly under `dist/` are historical and must not be uploaded.

- [Project licence decision](project-license.json): Apache 2.0 selection and official text hash.
- [Qualification results](qualification.json): exact wheel and source archive
  hashes, archive contents checks, installed dependencies, and smoke results.
- [Release manifest](release-manifest.json): binds those artifacts, the SBOM,
  and the qualification context; retains the pending licence decisions.
- [Qualification context](qualification-context.json): platform, base commit,
  working-tree status, and hashes of the supporting evidence files.
- [SBOM](sbom.cdx.json): inventory exported from the lock with all groups and
  extras. This includes development and optional dependencies; the qualification
  results separately record the dependencies actually installed for each check.

The artifacts were built from the modified working tree, not a release commit.
Their version remains `0.1.0`, and the changelog marks them unreleased.

## Completed checks

| Check | Result |
|---|---|
| Full test suite (preceding technical qualification) | 641 passed, 40 skipped |
| Release tests after licence addition | 10 passed |
| Apache 2.0 packaging | Metadata and identical licence text verified in both archives |
| Ruff | Passed |
| Mypy | Passed, 157 source files |
| Existing probity evidence audit | Passed, 36 records across 11 gates |
| Sphinx with warnings as errors | Passed |
| Build wheel from source distribution | Passed |
| Distribution contents | 84 wheel files, 85 source archive files; no private docs, tests, tools, evidence, GDX, or GAMS restart files |
| Isolated base wheel install | Passed without development dependency groups |
| Native SCIP dispatch and HiGHS pricing | Synthetic reserve case completed |
| Installed report generation | All 12 tables written and read back with matching logical hashes |
| Optional GDX installation | Synthetic GDX write/read passed with the local GAMS runtime |

This qualification covers Python 3.13 on macOS ARM64. It does not establish
complete historical parity, qualify all optional solver backends, or replace an
end-to-end historical GDX application run. Skipped tests remain outside this
run's evidence. The existing historical qualification records remain separate.

The packaging changes install HiGHS by default, expose GDX/CLP/CBC/Probity extras,
bundle the build lock needed by report provenance, and explicitly restrict
distribution contents. CI now builds and qualifies an installed wheel after
the normal tests and documentation build. The CI smoke check does not require
the optional GAMS runtime.

## Before public release

1. Resolve the release-critical rows in the
   [licence register](../docs/gate-0/licence-and-provenance-register.md) and add
   any required third-party notices. The Apache 2.0 project licence and package
   metadata are in place.
   These decisions cannot be inferred from passing engineering tests.
2. Confirm the intended release scope and version. A broader platform or parity
   claim requires corresponding qualification. Update the changelog and version
   before the final build.
3. Commit the reviewed changes and pass CI on that commit. Rebuild, repeat the
   installed qualification, and regenerate the SBOM and release manifest after
   any packaged content or dependency change. The manifest must reflect the
   actual approved licence decisions before distribution.
4. Confirm PyPI project ownership and configure the publishing identity or
   trusted publisher. No package-name availability or account access has been
   verified in this preparation. Test the selected final artifacts through the
   intended staging publication process before uploading to PyPI.
5. Connect the repository to Read the Docs, pass a hosted build using
   `.readthedocs.yaml`, and verify its public URL. The current RTD preview is
   local; add the verified hosted URL to the package metadata and README before
   the final build.
6. Tag the release commit and publish only the exact artifacts covered by the
   final permitted manifest.

## Reproduce the technical checks

Run from the repository root:

```shell
uv sync --frozen --group docs
uv run --no-sync ruff check .
uv run --no-sync mypy src tools
uv run --no-sync pytest -q
uv run --no-sync python -m tools.probity_audit
uv run --no-sync sphinx-build -W --keep-going -b html docs site
uv build --no-sources --out-dir dist/candidate
uv run --no-sync python -m tools.qualify_distribution \
  --artifacts dist/candidate --output private/release-readiness
uv export --format cyclonedx1.5 --frozen --all-groups --all-extras \
  --output-file private/release-readiness/sbom.cdx.json
```

To repeat the optional GDX check, append `--gams-system-directory` with the
local GAMS system directory to the qualification command. Use a fresh artifact
directory when changing versions: the qualifier requires exactly one wheel and
one source distribution.

The `red.log` and `green.log` files record the targeted regression for installed
provenance and dependency metadata. The full test, build, installation, type
check, and evidence audit outputs are retained beside this file.
