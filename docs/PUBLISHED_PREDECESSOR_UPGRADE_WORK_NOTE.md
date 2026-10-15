# Published predecessor upgrade qualification

- Status: active; qualification results and accountable disposition will be recorded in the delivery PR.
- Review at delivery acceptance; do not reuse this qualification for a changed candidate.
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

The signed preparation head is `35cfe63accc209173d146da97899c1193bf4117b`.
[Native build run 38655733779](https://github.com/joshuamyers22/mos-eisley/actions/runs/38655733779)
passed all four targets. Its actual PR merge checkout is
`d8b05adb6e2fa1d1cbe6aa73b2c2c453f35e6278`; both commits have tree
`773fbb5c337229bb151a94b30e9f9ad789bb4b1d`. Native records bind that actual checkout,
archive hashes and bootstrap hashes. The existing owner-operated signer prepared
[public signature/hash metadata](qualification/rc2-upgrade-candidate.json) for those
unchanged archives. No private key is retained. This is an unpublished preview
candidate, not permission to publish `rc.2`.

`tools/qualify_published_upgrade.py` executes both enrolled-key frozen installers,
both frozen runtimes and the public recovery/rollback/uninstall commands. Only
interruption timing is injected in the source installer. JSON and SQLite sessions
are created by rc.1, loaded by rc.2 and read again by rc.1 after candidate writes.
The separate read-only `published-upgrade.yml` matrix downloads the pinned candidate
run and immutable public predecessor; its evidence records hashes and outcomes,
never session contents or credentials. All 37 focused distribution checks passed,
along with Ruff and strict Pyright. Final native/local/quality results and acceptance
are maintained in [delivery PR #305](https://github.com/joshuamyers22/mos-eisley/pull/305).

This workflow qualifies the pinned rc.1/rc.2 pair. GitHub build-artifact retention
limits future replays; a later candidate must supply fresh passing native artifacts,
the recorded checkout identity and newly reviewed signed metadata. A changed
runtime, dependency lock, storage schema or storage epoch needs a new qualification.
Package-manager upgrade behavior remains a separate gate from this standalone journey.

The local enrolled-key macOS ARM journey passed, including both storage backends,
candidate-written-session rollback, both interruption points, tamper refusal and
uninstall/reinstallation. Initial CI lifecycle steps passed but evidence upload
failed because the pinned uploader excludes hidden `.work` paths. The corrected
workflow writes only the compact qualification result into `dist/qualification`;
the final all-platform run must pass and retain all four evidence files. That
failed retention run remains attributed in the delivery PR, not counted as a
passing workflow. No runtime or signature control changed to address it.
