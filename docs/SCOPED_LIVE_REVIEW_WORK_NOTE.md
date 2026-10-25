# Scoped live-review connection work note

Status: complete; implemented and verified. Owner: Joshua Myers. Base: `49bc9c7`.
Branch: `feat/scoped-live-review`. Requirement: §31.7 launch-preview/live connection
and §31.1 preview, preserving existing signed admission and read-only authority.

Guidance: Python engineering guide, bounded verification guide/loop, work-note and
threat-model templates from pinned production template
`8879be48f3b760e65f6bed32f8740314fe92910d`.

Objective: connect an explicitly selected, complete Git scope to its exact prepared
live brief and show shared inert launch metadata before dispatch. Never rebind a
recording, signed decision, campaign or model request to an arbitrary diff.
Blocking invariants: owner/workspace/brief identity; fresh source/configuration,
guidance/policy and spending; existing quorum, separate launch/phase signatures,
one-use attempts, cancellation cleanup and no writes or publication authority.
Preserve prepared-packet compatibility and exact-launch qualification boundaries.

Material security/financial integration. Three evidence passes: shared contracts
and focused boundary fixtures; real synthetic Git scopes with controller/UI/CLI,
stale-source and cancellation faults; standard sequential source/coverage/build/
installed-wheel gate. Ceiling: four hours active engineering plus the normal gate,
three evidence-changing passes; no paid calls or real owner session catalogs, credentials
or signing records; synthetic fixtures only. Stop at passing gates; never weaken signatures or replay
uncertain operations to make a test pass. Accountable production/live activation
remains outside this implementation request.

Threat model: untrusted source/criteria cannot alter policy, expand read scope,
enter critic context as conversation history, or authorize creator/posting work.
Saved packets retain source/brief identities, never credential/signing paths or
launch authority. Changed sources must fail before later credential/provider use
and before a result becomes conversation evidence. Preview cannot reserve funds,
load keys, create a run, contact providers or grant launch authority. Live paid
execution retains the existing owner-operated admission ceremony and containment.

Passes 1–2: 77 focused tests passed: 10 new scoped live integration, 11 existing
live conversation, 24 launch preview, 20 scoped ranges and 12 launch conformance.
New evidence covers original-source versus guided-brief identity; CLI plain/JSON
and conversation projection parity; inert preview with unchanged source/index/
HEAD/configuration/ledger; owner/workspace, changed config/policy, quorum and cap
rejections; child admission callbacks stopping stale inputs before credentials;
source changes during review and approval; suppressed stale result display;
recorded guided-scope compatibility; both session stores and consumed cancellation.
The full-screen integration uses a 30-second bound for real bounded Git acquisition,
rather than the three-second helper used for in-memory UI fixtures. No existing
security or authority assertion was relaxed. Existing child reaping remains intact.

Decisions: optional canonical scope/hash fields preserve legacy selection bytes;
schema-2 live packets require the complete scope and exact original source brief.
The prepared brief remains the exact guidance projection used for signed launch.
Shared previews add no prompt or authority; the existing separate signed phase
and local approvals are unchanged. Paid conversational dispatch retains its
interactive owner ceremony; plain/JSON previews are inert, and scriptable events
retain separate stderr diagnostics. No platform or new-target qualification is
inferred. The package smoke suite now explicitly includes existing live-review
fixtures and the new scoped integration tests.

Pass 3 complete: `make check -j1` exited 0. Ruff lint/format and strict Pyright
passed. The source suite passed 3,833 tests in 2,981.707 seconds (17 existing
skips). Total coverage is 86%, above the 84% threshold. Runtime export verification,
source/wheel builds and fresh installed-wheel checks passed. The installed suite
passed 2,811 tests in 2,095.049 seconds (13 existing skips), including the existing
live-review fixtures and all 10 scoped connection cases. No authority assertion
was relaxed. Full disposable log: `/private/tmp/mos-scoped-live-check.log`.

All 412 package Python source files match the tested wheel bytes. Wheel SHA-256:
`86909ad1d7e6597a15f300cdd3b42efe1927abeff9d7cf44c0273fef103529c2`.

No unresolved blocking finding remains for the shared preview/scoped live
connection. No dependency or spending reset was introduced. Existing signed launch
and phase decisions, exact local approvals, quorum, consumed attempts, child
reaping and read-only/no-posting authority remain authoritative. No paid call or
real owner-data inspection occurred. Managed-worktree, supported-platform and
exact new-target/live release qualification remain separate; this work supplies
no production activation or signing authority.
