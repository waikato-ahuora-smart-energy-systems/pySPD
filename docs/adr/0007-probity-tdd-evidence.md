# ADR-0007: Probity and auditable TDD evidence

| Field | Value |
|---|---|
| Status | Accepted by explicit project direction |
| Date | 28 August 2026 |
| Deciders | Project direction; technical implementation agent |

## Context

The repository has a Probity `PreToolUse` hook that guards supported interactive
changes. A local agent hook is useful but cannot independently prove that every
production change began with the expected failing behavioral test. A lint,
import, missing dependency, or environment failure is not valid red evidence.

## Decision

Use both controls:

1. Probity remains the immediate interactive TDD guardrail for `src/**`, package,
   `tests/**`, and `tools/**` changes.
2. CI requires a red/green record conforming to the
   [TDD evidence schema](../gate-0/schemas/tdd-evidence.schema.json) for every
   changed production path.

The red record binds:

- requirement IDs and production paths;
- parent commit;
- test patch/blob hashes;
- exact command and environment manifest;
- nonzero exit and expected behavioral failure fingerprint; and
- output hash and timestamp.

The green record binds the same test to the implementation state, zero exit,
environment, command, output hash, and reviewer. Python commands use `uv run`.

Exceptions require a material reason, independent approver, expiry, and named
follow-up test. A missing or mismatched record blocks merge and the relevant
gate. Golden files may originate only from a pinned oracle or approved hand
calculation, never PySPD itself.

## Consequences

- TDD becomes independently reviewable instead of a process assertion.
- CI/artifact storage must retain small signed/hash-addressed records.
- Some mechanical changes need an explicit, reviewed exception.
- Test-first history survives rebases when hashes and parent context are
  preserved in the evidence record.

## Rejected alternatives

- **Probity hook alone:** bypassable and not durable audit evidence.
- **Line coverage as TDD proof:** says nothing about test-first behavior.
- **Commit ordering alone:** tests and production often share a commit and
  rebases rewrite history.
- **Any nonzero exit counts as red:** accepts infrastructure failures rather
  than behavioral characterization.

## Verification

- Gate 2 CI negative tests reject missing, wrong-parent, wrong-test, wrong-error,
  expired-exception, and hash-mismatched records.
- Component definition of done links requirement, red, green, matrix, and oracle
  evidence.
- Gate manifests include TDD ledger hashes.
- Independent validation samples records and reproduces red/green runs.

## Revisit triggers

- Probity provides signed durable evidence with equivalent semantics.
- Repository workflow changes make the schema insufficient.
- Auditors require stronger signature/attestation controls.
