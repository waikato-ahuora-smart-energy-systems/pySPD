# Automatic releases

Pull requests to `main` prepare a release version before validation, following
OpenPinch's label and title convention:

| PR control | Example from 1.2.3 |
|---|---|
| No version label or title tag | 1.2.4 |
| `patch` label or `[patch]` in the title | 1.2.4 |
| `minor` label or `[minor]` in the title | 1.3.0 |
| `major` label or `[major]` in the title | 2.0.0 |

Labels are case-insensitive and take precedence over title tags. If several
version labels are present, `major` wins over `minor`, then `patch`. These are
PR labels or bracketed title tags, not Git tags named `major` or `minor`.

For branches in this repository, the workflow commits the bump to the PR
branch. It updates `pyproject.toml`, `pyspd.__version__`, the root package in
`uv.lock`, and the release links and wheel examples in the installation docs.
Dependency versions and historical release records stay intact.

The target is calculated from the current `main` version. Repeated events do
not bump again. Adding a larger label upgrades the candidate; removing a
label never lowers an already prepared version. An explicitly higher version
is preserved. If the branch is behind `main`, update it before retrying. Fork
PRs must update their versions themselves because the workflow cannot push to
the fork.

PR runs are serialized to avoid interrupting a version commit. The read-only
`pr-gate` validates the exact prepared commit. If the bot pushed a new commit,
a separate job records that validation result on its SHA; this does not rely
on a token-generated push starting another CI run. Version preparation failure
fails the required gate.

Merging to `main` checks that the version advanced and creates an annotated
`vMAJOR.MINOR.PATCH` tag on the merge commit. An existing tag must point to that
same commit. The workflow explicitly dispatches `publish-pypi.yml` at the tag,
because tag pushes made with `GITHUB_TOKEN` do not trigger push workflows.

The tag run performs source and documentation validation, builds the wheel and
source archive, and qualifies an isolated installed package. The tag, both
archives, runtime version, and bundled lock must agree. Only then does PyPI
trusted publishing upload those artifacts. A GitHub Release with the same tag
and artifacts is created after publication succeeds.

The repository needs Actions write permission for the bump job and the existing
PyPI trusted publisher for `publish-pypi.yml`, environment `pypi`. The publishing
job runs at the release tag, preserving that deployment context. No personal
access token is required. Direct pushes to `main` must already contain a forward,
synchronized version; the automatic bump happens in the PR.

For a failed publication, rerun the failed jobs in the original tag run. The
existing PyPI check skips already uploaded files; GitHub release retries verify
existing assets instead of replacing them. Do not move an existing release tag.
