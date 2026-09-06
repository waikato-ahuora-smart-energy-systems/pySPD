# PyPI 0.1.0 publication

The user explicitly instructed: **"Publish to Pypi"** on 2026-09-06, after
selecting Apache 2.0 and reviewing the remaining release work. This is the
publication instruction for `pyspd==0.1.0`; it does not represent a legal review
of third-party materials or change the historical LIC records.

The candidate manifest and qualification context in this directory describe
the preceding preparation run. Their pending decisions and hashes are retained
as historical evidence. The final release is rebuilt and tested from its tag;
the GitHub Actions run retains the exact distribution artifacts and a separate
qualification report containing their hashes and installed dependency versions.

Publication uses `.github/workflows/publish-pypi.yml` in
`waikato-ahuora-smart-energy-systems/pySPD`, triggered by `v0.1.0`. The tag must
match the package version. Source validation, the strict documentation build,
archive inspection, and an isolated native SCIP/HiGHS solve with all twelve
report tables must succeed before the publishing job starts. The publishing
job consumes the qualified archives and uses PyPI OIDC in environment `pypi`.
It receives no repository write permission or long-lived PyPI credential.

Only the wheel and source archive are uploaded to PyPI. Private records,
external GDX inputs, and solver evidence are excluded by the package file list
and archive qualification checks. The optional GDX adapter was also exercised
locally; hosted qualification uses the base installation without GAMS.

The hosted Read the Docs URL remains a separate follow-up. For this release,
the package README links to the documentation source at the release tag.
