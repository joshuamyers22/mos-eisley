# Principal and file-identity contract definition

Status: definition complete; implementation/native qualification pending. Started: 2026-10-03. Owner: Josh Myers. Base: f8a8e94
(PR #258), clean `docs/platform-identity-contracts` worktree.

Objective: define the next bounded §27.2 batch, including tagged value types,
principal semantics, opened-object identity, failures, compatibility boundaries
and implementation acceptance tests. This task defines contracts; it does not
implement adapters, change authorization or migrate retained artifacts.

Selected guidance: [architecture playbook](ADVERSARIAL_REVIEW_PLAYBOOK.md),
[review template](../templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md),
[ADR template](../templates/ADR.md), [threat model](../templates/THREAT_MODEL.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md) and
[work-note template](../templates/WORK_NOTE.md).

Blocking rubric: each platform has explicit identity/equality scope and an OS
source; no identity value grants authorization; no path-stat race or UID/SID
coercion; legacy bytes and hashes remain intact; native tests are specified without
claiming execution. Risk: material design for an ownership boundary. Budget: two
source/specification passes and 45 minutes; stop on an implementation-ready bounded
specification. Native implementation/release requires separate accountable review.

Evidence: source and representative regression tests plus primary Python/Microsoft
platform documentation. Checks for this documentation-only batch are trace/link
validation and diff checks; the inherited f8a8e94 combined gate passed previously
and will not be represented as an identity-contract runtime test.

## Source/specification passes and findings

1. Traced current-principal and device/inode use in conversation, memory, guidance,
   SQLite and directory/relocation consumers, with representative regression tests.
   Kept retained schemas and existing combined authorization checks outside the
   proposed additive implementation. Reviewed Python and Microsoft API references.
2. Checked the proposed contract against impersonation/error fallback, full-width
   file IDs, native SID pointer lifetime, descriptor/HANDLE confusion and stale
   observations. Added explicit bounds-before-native-validation, context/lifetime
   preconditions and separate POSIX/native implementation PRs.

| Finding | Disposition and evidence |
|---|---|
| A UID/SID or file-ID match is insufficient authorization | Keep policy and common-scope establishment at storage/effect boundaries; contract and threat model state residual limits |
| Retained identities already affect apply/snapshot hashes | No new codec/writer in the additive batch; migration gets its own acceptance gate |
| Querying an open object does not bind SQLite's separate opens | Preserve existing root/private/connection policy; no replacement claim |
| Native context and filesystem eligibility need real evidence | I-06–I-08 remain future qualification gates; detect/inspect local NTFS and freeze supported targets before native admission |

## Verification and handoff

- Twenty-one local documentation targets resolved; seven source/regression symbol
  trace checks passed; `git diff --check` passed.
- Changes are documentation only: proposed ADR-0014, contract and threat/work
  records, plus plan/roadmap/memory links. No runtime, tests, CI, dependencies,
  retained artifacts or executable contract were changed. Runtime suites were not
  rerun; inherited f8a8e94 evidence is for the reader batch only.
- I-01–I-09 specify required implementation evidence; none is presented as newly
  executed identity-adapter evidence. No native qualification or release approval
  is claimed. Stop reason: definition rubric satisfied within the declared scope.
- Proposed architectural decision and durable memory key are linked to
  [the specification](PLATFORM_IDENTITY_CONTRACTS.md) and
  [ADR-0014](adr/0014-platform-identity-contracts.md).
- This worktree is based on PR #258 and must follow its merge/rebase outcome before
  publication. It leaves the reader PR and earlier survey edits intact. This batch
  is recorded on `docs/platform-identity-contracts`; no push or PR performed.
- Next smallest implementation: additive pure tagged values and POSIX queries,
  Windows/unknown-platform refusal, isolated source/wheel tests and scoped CI.
  Native read-only adapters and schema adoption remain separate batches.
