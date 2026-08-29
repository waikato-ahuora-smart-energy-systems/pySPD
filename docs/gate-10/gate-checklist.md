# Gate 10 checklist

| Criterion | Evidence | Decision |
|---|---|---|
| Immutable canary baseline | `CanaryBaseline`; mutation regression | PASS |
| Mismatch quarantine without baseline rewrite | append-only `QuarantineStore`; duplicate-write regression | PASS |
| Hash-bound wheel, sdist, SBOM, and evidence | `release-manifest.json`; read/tamper tests | PASS |
| Missing artifact fails closed | release builder regression | PASS |
| Frozen uv setup and package build | `uv sync --frozen`; `uv build` | PASS |
| Isolated wheel installation and CLI smoke | temporary uv venv reports v5 formulation | PASS |
| macOS CI and Linux deferral | workflow contract test | PASS |
| Documentation and operational controls | `README.md`; release handbook | PASS |
| Dependency provenance | CycloneDX 1.5 SBOM from all locked groups | PASS, LEGAL REVIEW PENDING |
| Legal/notice decisions | Gate 0 `LIC-001`–`LIC-014` | HOLD |
| Public distribution | all legal decisions must permit release | HELD |
| Independent validation reviewer | removed by project direction | NOT APPLICABLE |
| Strict parity/CPLEX/T4/full-day | Gate 12 | DEFERRED |

Decision: **Gate 10 engineering release controls are closed at the amended
evidence boundary. Public distribution remains held.**
