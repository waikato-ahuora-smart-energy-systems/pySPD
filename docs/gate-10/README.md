# Gate 10 engineering release-control evidence

Gate 10 is closed at the project-amended engineering boundary. The controls
are usable and verified, but public distribution remains held by Gate 0 legal
and licensing decisions.

| Artifact | Purpose |
|---|---|
| `closure-decision.md` | Scoped gate decision and exclusions |
| `gate-checklist.md` | Criterion-by-criterion result |
| `release-handbook.md` | User, developer, security, support, rollback, and canary procedures |
| `release-manifest.json` | Hashes artifacts, SBOM, evidence, formulation, and legal status |
| `sbom.cdx.json` | uv-generated CycloneDX 1.5 inventory of all locked groups |
| `dist/.gitignore` | Keeps locally reproduced wheel/sdist out of source control |
| `tdd/` | Red/green Probity evidence and environment |

Reproduce the ignored artifacts with:

```shell
uv sync --frozen
uv export --format cyclonedx1.5 --frozen --all-groups --output-file docs/gate-10/sbom.cdx.json
uv build --out-dir docs/gate-10/dist
```

The checked-in release manifest records the exact artifacts built during Gate
10. A later rebuild is expected to produce a new candidate manifest and must
not silently replace an accepted baseline.
