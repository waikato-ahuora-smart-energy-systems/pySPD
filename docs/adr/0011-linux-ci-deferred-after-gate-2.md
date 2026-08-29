# ADR-0011: defer Linux x86_64 execution after Gate 2

| Field | Value |
|---|---|
| Status | Accepted by explicit project direction |
| Date | 29 August 2026 |
| Deciders | Project direction |

## Context

Gate 2 qualified the locked package, canonical runtime, GDX conversion, Pyomo
assembly, and HiGHS LP backend on macOS arm64. A Linux x86_64 workflow is
configured but has not been executed because repository publication was not
authorized. Project direction explicitly instructed the gate to skip that run.

## Decision

Linux x86_64 execution is deferred and does not block Gate 2 or Gate 3. Gate 2
closes only for the qualified macOS arm64 profile. No Linux compatibility,
logical-hash portability, solver, or release-readiness claim may be inferred.

The configured Linux job remains mandatory before Linux becomes a supported
platform or any release includes a Linux portability claim.

## Consequences

- Gate 2 can close without an external repository mutation.
- Stage 3 may proceed on the qualified macOS profile.
- Cross-platform logical-hash evidence and Linux dependency/runtime evidence
  remain open and must be recorded before Linux support is advertised.

## Verification

- Gate 2 evidence states the qualified platform explicitly.
- Compatibility and dependency registers mark Linux deferred by this ADR.
- CI retains the Linux job for later execution.

## Revisit triggers

- A branch is pushed to a repository capable of running the configured job.
- Linux becomes a requested development, deployment, or release platform.
