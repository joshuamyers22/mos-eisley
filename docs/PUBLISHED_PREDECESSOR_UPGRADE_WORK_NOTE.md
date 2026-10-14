# Published predecessor upgrade qualification

- Status: active; qualification results and accountable disposition will be recorded in the delivery PR.
- Owner: Joshua Myers
- Started: 2026-10-14 UTC
- Starting main: `4df32f89ff6c864a7cc8b5d66c1406e69f2e66b7`; prepare unpublished `0.1.0-rc.2` native artifacts at the signed preparation commit recorded in the delivery PR.
- Predecessor: immutable published `0.1.0-rc.1`, source `8cf38c83591e505a9c7b57f4d701b12cb80fc4c6`.

## Objective and authority

The owner requested real-predecessor upgrade qualification: preserve saved sessions,
recover interrupted activation, explicitly roll back and uninstall using the actual
published version. The next candidate is an unpublished development artifact;
qualification does not authorize a version tag, application release, npm publication
or tap update. WSL2 remains postponed.

The isolated worktree starts clean at the candidate commit. Selected guidance is
`AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/WORK_NOTE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md` and `templates/THREAT_MODEL.md`.

## Blocking acceptance rubric

| Dimension | Required evidence |
|---|---|
| Real predecessor identity | Untouched published archive, enrolled-key metadata and native bootstrap; immutable release identity and digest checks. |
| Candidate identity | Existing four native build artifacts at the exact source commit, enrolled-key signed inventory, exact version and hashes. |
| Session compatibility | Published runtime creates recorded JSON and SQLite sessions; cold resume before/after replacement and after rollback; no paid calls. |
| State integrity | Session, credential/config and spending sentinels remain byte-identical across installation, refusals, recovery, rollback and uninstall; only explicit recorded turns may change session data. |
| Failure handling | Interrupt before and after the activation commit; recover the expected version, clear pending transaction, and retain sessions. Reject archive/runtime tampering. |
| Native execution | Execute both actual frozen versions on macOS/Linux arm64/x86_64 without external Python or Node on PATH; frozen CLI recovery/rollback/uninstall on ordinary paths. |
| Delivery | Focused checks, one combined `make check`, exact-head CI, four native qualification results and accountable owner acceptance. |

## Trust boundaries and stopping rules

Published predecessor and candidate use the already enrolled public root. The
existing owner-operated signer reads the external private key directly; no private
key, encoded key or credentials enter Git, logs or retained artifacts. Candidate
metadata contains public hashes/signatures only. No publisher trust bypass is
permitted. Fault injection changes only the interruption point in the source
installer; parsing, archive verification, executable verification and recovery
remain intact. Frozen CLI operations provide a separate unpatched execution path.

All journeys use fresh private disposable roots, synthetic recorded conversation
content and inert credential/config/spending sentinels. Real user stores, provider
credentials and sampling/evaluation stores are outside scope. Signed candidate
metadata is preparation evidence, not stable acceptance or freshness evidence.

Budget: at most three evidence-changing implementation/fix passes, one full local
quality gate and one final exact-head CI matrix; no provider spend. Stop on wrong
signature/source/platform/version, state loss, failed cold resume or a publication
mismatch. New runtime/schema changes require new artifacts and qualification.

## Observations and handoff

The existing native smoke journey uses synthetic `0.0.0` metadata on the candidate
code. This task replaces that historical-compatibility assumption with untouched
published predecessor artifacts. Main changed documentation/publication tooling
since rc.1; this pair does not prove compatibility with future runtime/schema changes.
Exact results and source/artifact identities will be recorded in the delivery PR.
