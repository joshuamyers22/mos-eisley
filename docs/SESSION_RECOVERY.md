# Session and execution recovery

Mos retains recovery evidence in the existing private owner/workspace-scoped JSON
snapshot or SQLite session. The execution container is disposable. Resume verifies
the session's identity, hashes, typed records and bounded context before continuing;
it does not read a sandbox transcript or create a second transcript database.

## Durable operations

Each newly dispatched author/review turn, side question, fork publication, local
child attempt and coding integration has a stable operation ID derived from the
session ID and immutable operation key. A nested version-1 `recovery_journal`
records contiguous, monotonic event sequences and session revisions. Its dispatch
decision binds hashes of the applicable admission/policy, target, request and
resource reservation. Payloads remain in their original session entries/artifacts;
the journal contains no duplicate prompts, answers, tool arguments or credentials.

The dispatch decision, consumed attempt and existing goal/branch reservation are
committed together before execution. A successful result and terminal journal event
are committed together before the recovery cursor advances. The cursor is the last
committed terminal-event sequence, not permission to ignore an earlier open
operation: every open operation is inspected on restart. The complete admitted
turn is the recovery unit; intermediate model/tool calls are never replay cursors.

Paid admission still reserves its full monetary exposure in the existing shared
spending ledger before network dispatch. The session decision binds that policy
and ledger identity; it cannot settle, refund or recreate a ledger reservation.
Loss of a controller, response, sandbox or completion acknowledgement never resets
the aggregate ledger. Exact evidence-bound reconciliation retains its existing
separate authority requirements.

## Failures and continuation

| Failure | Recovered behavior |
|---|---|
| Dispatch transaction fails before commit | No dispatch; queued work and unconsumed attempt remain |
| Dispatch commits but acknowledgement is lost | Open dispatch becomes uncertain even if no call actually started |
| Controller or sandbox disappears after dispatch | Turn becomes interrupted; its effect is explicitly uncertain; child/integration/side/fork recovery preserves its existing conservative state |
| Result transaction fails | Last durable dispatch remains uncertain; no answer is claimed |
| Result commits but acknowledgement is lost | Verified committed result remains completed; it is not executed again |
| Cancellation or execution failure | Full unresolved exposure remains; the uncertain event closes the operation without granting retry |

TUI and plain output display an uncertainty notice. JSON message events expose
`effect_status`, `operation_id` and `recovery_cursor`; `mos exec` exposes the same
operation metadata in its terminal result after a successful persistence boundary.
Review verdicts remain separate from operation completion. A failed persistence
boundary still suppresses result claims, requiring a verified reopen.

Use ordinary explicit `mos resume` to reopen. Outstanding queued steering survives,
including links to an interrupted request. Fresh queued work uses the remaining
budget and current admission; it cannot repeat a previous consumed operation.
Verified read-only work may continue as a new admitted operation from committed
context. The controller deliberately does not resume halfway through a tool loop,
even when its last tool was read-only. Uncertain writes and paid calls require the
existing exact reconciliation workflow rather than an automatic retry.

## Replacement execution boundary

Tool-bearing turns bind the trusted current workspace/source observation. Text-only
turns bind the owned workspace identity and have no repository-revision target.
The controller rechecks the binding after dispatch persistence and before every
agent model/tool call, including calls within explicit live runners. Tool schemas
must still match the admitted capabilities. A changed workspace or schema stops
execution; existing tool-specific authorization remains required.

Every container exchange creates a fresh worker from an explicit immutable image
ID, with the existing fixed no-network, no-host-mount recipe and resource limits.
The container object freezes its trusted recipe; mutated image, executable,
capabilities, mounts or argument-dependent flags fail before launch. Workspace
admission is checked again before starting a created worker. Image inspection still
rejects implicit volumes. Coding snapshots/protected tests, creator approval,
workspace revision, scoped Git broker and integration authorization retain their
existing checks. Cancellation awaits owned cleanup; startup never reattaches or
automatically replaces a worker for an uncertain operation.

Docker child adapters also persist the exact recipe digest in the existing child
record and bind it into the journal decision. Execution and later coding
verification/integration compare the active adapter against that retained digest.
A replacement adapter with different privileges, mounts, executable or image
cannot reuse the saved child admission. Legacy records remain inspectable without
inventing a missing recipe; they cannot acquire a new Docker recipe through resume.
Trusted injected non-sandbox fixture executors keep their existing explicit test
contract and do not constitute Docker qualification.

## Bounds, compatibility and verification

The journal has at most 96 metadata events, covering the existing maximum 16 turns,
16 side questions, eight forks, four children and four integrations. It uses the
existing session/header byte limits; an oversized candidate fails before dispatch.
SQLite keeps archived artifact values out of the active working context, while
full verification and normal context selection remain mandatory on cold resume.

Legacy sessions without a journal remain readable and retain consumed attempts.
An old running entry becomes interrupted with a visible uncertainty notice; Mos
does not invent a missing historical policy or reservation. New journal-bearing
sessions require a compatible reader. Older binaries reject the added field;
rollback requires retaining a matching application and pre-change session backup.
Unknown journal versions, reordered events, duplicate operations, invalid cursors,
cross-session IDs and mismatched retained results fail closed.

[Recovery tests](../tests/test_conversation_recovery.py) exercise real stores,
abrupt subprocess exit, dispatch/result commit and acknowledgement faults, retained
steering, full real-ledger holds with synthetic providers, cross-owner/workspace
refusal, and shared TUI/plain/JSON projection. Existing child, live coding, storage,
bounded-context and container suites cover their dependent boundaries. The same
tests are included in the isolated installed-wheel gate. These are engineering
checks; credentialed live operation, native platform qualification and release
approval keep their existing scope.
