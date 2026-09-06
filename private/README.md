# Internal project records

This folder holds repository-only engineering material. It is outside the
Sphinx source directory (`docs/`) and is not included in Read the Docs pages, navigation,
search indexes, or static downloads. Its access permissions are those of the
repository; the folder name does not create an additional security boundary.

- [Engineering record and gate index](docs/engineering-record.md)
- [Architecture decisions](docs/adr/README.md)
- [Stage-and-gate plan](docs/pyomo-vspd-stage-gate-plan.md)
- [Architecture and extension contracts](docs/developer-guide/architecture.md)
- [Testing and evidence](docs/developer-guide/testing-and-evidence.md)
- [Documentation maintenance](docs/developer-guide/documentation.md)
- [Package release preparation](release-readiness/README.md)
- [Research development portfolio](docs/case-studies/potential-builds.md)

User documentation belongs in [docs/](../docs/index.md).

## Historical evidence paths

The gate directories and their associated JSON certificates and logs were moved
from `docs/` to `private/docs/`. Machine evidence retains its original bytes,
including historical paths and hashes. Current tools translate historical
`docs/gate-*` and `docs/research` paths when reading those records.

The immutable v1 solver archive retains `docs/gate-12` member names. Restore it
under the private root:

```shell
uv run pyspd evidence fetch gate12-solver-paths-v1 --destination private
```

Other archives contain test fixtures and still use `--destination .`. Archive
building preserves the original v1 member names. Large raw observations remain
ignored by Git; compact certificates and logs remain versioned here.
