# Recorded conversation preview

Bare `mos` (also `mos chat`) keeps a text conversation across messages and saves it
privately. Run it from your project directory; the built-in recorded preview and
`~/.mos-eisley-sessions` storage require no setup. Use `mos resume --last` to return
to that workspace's latest session. See [terminal startup](CONVERSATION_TUI.md)
for workspace selection, custom recordings and keyboard controls.
New sessions also load enabled [user/project memory](CONVERSATION_MEMORY.md).
`--no-memory` bypasses loading; saved sessions retain their effective revisions.
A terminal opens the [interactive screen](CONVERSATION_TUI.md) automatically;
`--plain`, pipes and `--json` use the line-oriented interface.
`mos resume <session-id>` explicitly restores that conversation in the same
workspace. `mos sessions`, `mos resume --last` and `mos session-delete` provide
navigation for the selected workspace and manual retention. This preview uses
request-bound recorded responses: it does not generate arbitrary answers or call a live provider. Every recorded response
must match the hash of the full current request, including prior completed turns.

## Try it

Run these commands in the same workspace. Use a new output filename and storage
directory; an existing storage directory must already be private (mode 0700).
The storage parent must exist. Mos prints the destination before writing.

```sh
mos conversation-demo --output /tmp/mos-chat-cassette.json
mos chat --cassette /tmp/mos-chat-cassette.json --storage /tmp/mos-chat-sessions
```

The demo contains exactly these two user messages, in order:

```text
Remember that the fixture boundary is ten.
What boundary did I give you?
```

Enter the first message and wait for its answer. Enter `/quit`, then use the
printed session ID to reopen the conversation and enter the second message:

```sh
mos resume <session-id> --cassette /tmp/mos-chat-cassette.json --storage /tmp/mos-chat-sessions
```

`--workspace /absolute/workspace` explicitly selects the workspace (default: the
current directory). Selecting a workspace does not read its repository files.
Resume requires the same canonical workspace and exact cassette, except for an
explicit [memory refresh](CONVERSATION_MEMORY.md#session-consistency-and-retention)
that preserves consumed exchanges and retains its replacement recording. A new `chat`
starts empty and never retrieves other sessions' content.

## Finding and removing sessions

List saved sessions for the current workspace, newest first:

```sh
mos sessions --storage /tmp/mos-chat-sessions
mos sessions --storage /tmp/mos-chat-sessions --json
mos resume --last --cassette /tmp/mos-chat-cassette.json --storage /tmp/mos-chat-sessions
```

Listings show session IDs, last-save filesystem timestamps, message counts,
active/available status and the exact snapshot hash. JSON includes revision,
completed/pending counts and nanosecond modification times. No transcript text is
returned. The adapter validates bounded snapshots owned by the current user before
filtering to the selected canonical workspace; it writes no catalog or additional copy.
Listing an empty existing store succeeds. Missing storage produces an error and
is never created by listing, resume or deletion.

`--last` selects the most recently modified snapshot observed in that workspace.
Tied timestamps use descending session ID for deterministic selection. Recency
comes from filesystem metadata and can change when files are restored or touched.
The catalog is not an atomic snapshot across sessions. Resume acquires the selected
session's exclusive lock and rechecks its hash before restoring context. Busy or
changed selections, a different cassette, or an invalid catalog entry fail the
operation. They do not cause a fallback to another session. Pending messages still
require explicit continuation, as with resume by ID.

To delete a saved conversation, replace `SESSION_ID` and `SNAPSHOT_SHA256` below
with values from a fresh listing:

```sh
mos session-delete SESSION_ID --expected-sha256 SNAPSHOT_SHA256 --storage /tmp/mos-chat-sessions
```

Deletion immediately removes that exact local snapshot. It requires the current
owner and canonical workspace, rejects an active session, and refuses a snapshot
that changed since selection. Under the session lock it validates and removes
only that session's private, singly linked temporary snapshot files, then removes
the committed snapshot and fsyncs the directory. Invalid targeted files stop the
operation before any removal. A cleanup failure can leave some temporary files
removed while retaining the committed snapshot for explicit retry; a final fsync
failure can mean removal occurred without durability confirmation. The command
does not automatically retry or report success after a failure.

The empty lock file remains to preserve synchronization with other handles. It
contains no transcript. Backup/version expiry and physical secure erasure are
outside this local operation. Orphan temporary files without any committed
snapshot still require manual inspection/cleanup. Automatic expiry and bulk
deletion are future work.

Use `--workspace /original/canonical/workspace` to list or delete records after
that workspace directory has been removed. Resume continues to require an existing
workspace. Catalog scans are limited to 4,096 directory entries, 256 candidate
snapshots and 8 MB of aggregate snapshot input by default. Each snapshot has a
saved byte budget, initially 2 MB and configurable up to 32 MB; the catalog scan
budget is independently configurable up to 128 MB. See
[storage budgets and expansion](CONVERSATION_STORAGE.md). Invalid or
over-limit catalogs fail instead of returning a partial selection. Retained lock
files count toward the directory limit. Use a dedicated private storage directory;
pagination and cleanup of unused lock files remain future work.

## Interaction and automation

The [interactive screen](CONVERSATION_TUI.md) and the `--plain` line-oriented
interface share user input, assistant answers, and visible
queued/running/completed/cancelled/interrupted/failed states. The line-mode
controls below are also available to pipes and JSON automation. The composer
accepts additional lines while a response is active. They enter a bounded queue
and apply after that response. Messages submitted during an active chat request
are now bound to its task as queued steering. Use `/compose` for a multiline
draft, then `/send` to queue it as one literal message in line mode. The screen
has an editable multiline composer with Enter to send. Mid-request interruption
remains future work.

- `/memory` inspects active user/project context. `/memory refresh` loads current
  saved memory; `/memory off` disables it for the session without reading storage.
  Stop or finish active work first. Successful changes save the selection and pause
  queued work until explicit continuation. See [memory management](CONVERSATION_MEMORY.md).
- `/stop` or Ctrl-C cancels the active request and queued messages, retaining their
  text and status, and discards an unsent draft. The session remains open for
  new input.
- `/review` or `Review this change.` runs a configured explicit recorded review
  packet and returns a bounded summary. See the
  [review workflow](CONVERSATION_REVIEW.md) for setup, isolation and evidence limits.
- `/quit` cancels active work, saves queued messages without executing them, and
  exits. Unsent drafts are discarded. On resume, `/continue` or a newly submitted
  message explicitly starts queued work; opening or editing a draft does not.
- EOF discards any unsent draft, finishes work already enabled in this invocation,
  then exits. Opening a resumed session followed by EOF only displays/saves it;
  it does not execute its
  pending messages. Ctrl-C remains effective while finishing work after EOF.
- `--json` emits NDJSON lifecycle events using the same controller. Input is still
  line-oriented, including the same compose/send/discard controls. Pipes, redirected
  files and terminals are supported. Control characters are escaped in terminal
  output.

There are at most 16 submitted messages per session and 8,000 characters per
message/answer. The existing agent request and response byte budgets still apply.
Each ordinary chat message permits one request, no tools, no retries, and a
30-second timeout. Explicit reviews use their separately bounded critic/judge
workflow and do not consume a chat cassette position.
Failed/cancelled/interrupted answers are excluded from future model context.
Their user text is included only when retained steering explicitly links to that
unanswered task; unrelated unfinished messages remain excluded. Completed messages include recorded usage; failed attempts retain
their consumed cassette position without inventing usage. A failed recorded
request pauses dispatch and emits an error; the session itself remains usable.
Unexpected text cannot match this synthetic demo's exact request hashes.

## Steering during work

Plain messages sent while a chat request is running are saved as refinements of
that task. `/steer TEXT` explicitly requires an active chat request; if it has
already finished, no message is queued and the session does not start work. Use
an ordinary message for a follow-up after completion. A draft binds to the task
active at `/send`, not when `/compose` opens. Inside a draft, `/steer TEXT` is
literal text, like `/review`.

The transcript labels each message with its zero-based index. Bound refinements
also show `steering message N`; NDJSON includes the same `steering_for` index on
queued, running and terminal lifecycle events. The snapshot saves that link
before publishing the queued event. Target indices must refer to earlier,
dispatched chat messages; review entries cannot be targets or carry steering.
Old snapshots without links preserve their canonical encoding. An older install
that does not understand steering fields rejects a new linked snapshot.

Steering applies at the next request boundary in FIFO order. It does not mutate
an already dispatched request, cancel it, replay it, or grant additional tool or
provider authority. If the target completes, its ordinary user/assistant context
is available to the refinement. Multiple refinements retain their submission
order and see earlier completed answers. General tool-boundary steering,
streaming and immediate status replies remain future work.

If the target fails, dispatch pauses with the refinement still queued. `/quit`
or process interruption also preserves a queued refinement; resume marks any
saved running attempt interrupted and waits for explicit continuation. On
`/continue`, the new request includes the unanswered original user text followed
by its refinement as separate text blocks in one user turn. Chained unanswered
refinements preserve the same sequence. No failed answer is invented, no prior
cassette position is reused, and later context retains the combined user turn
that actually received an answer. The existing request byte budget still applies
to this expanded intent. `/stop` cancels the active request and queued
refinements together, without erasing their text or links.

Reviews remain separate: `/steer` is unavailable while a review is running.
Ordinary input and sent drafts queue as unbound follow-ups after its report;
they cannot modify the selected packet or enter an in-flight critic request.
A newly requested review likewise remains a frozen packet rather than a chat
refinement. Recorded responses may complete immediately, so an explicit
`/steer` can correctly report that there is no active chat by the time it arrives.

## Multiline composition

Create a cassette for the multiline demo, then start a fresh session:

```sh
mos conversation-demo --multiline --output /tmp/mos-multiline-cassette.json
mos chat --plain --cassette /tmp/mos-multiline-cassette.json --storage /tmp/mos-multiline-sessions
```

Enter this sequence. Blank lines, indentation and code fences are part of the
single submitted message:

````text
/compose
Remember this fixture boundary:

```python
boundary = 10
```
/send
What boundary did I give you?
````

The first response remembers ten; the follow-up uses that completed turn. You can
quit after the first response and resume with the same cassette before sending
the follow-up. The `--multiline` demo is synthetic and still requires exact text.

- `/compose` opens one draft. Subsequent lines append to it; status events show
  its line and character counts. `/send` queues the entire draft through the normal
  durable controller. `/discard` drops it and returns to ordinary line input.
- `/compose`, `/send`, `/discard`, `/stop` and `/quit` remain controls in draft
  mode. Prefix a literal leading slash with another slash: `//send` inserts
  `/send`, and `///path` inserts `//path`. Other lines, including `/review`,
  `/continue` and `Review this change.`, become literal draft content. Sending
  a draft never invokes a review panel through text-intent routing.
- A draft allows 8,000 characters including inserted newlines and at most 256
  lines. Empty sends leave it open. Exceeding either limit invalidates the whole
  draft until `/discard`; it cannot submit a truncated paste. Submitted messages
  still obey the session's 16-message and agent byte limits. A full session leaves
  the draft open for explicit discard, without dispatching saved queued work.
- Drafting remains usable while chat or review runs. A sent draft queues behind
  active work and receives its completed context. During chat, it also retains
  a steering link to that active task; it does not alter a dispatched request.
  Merely drafting or discarding does not continue a paused session.
- Unsent drafts exist only in process memory. They are absent from snapshots,
  model requests and application event text, and are discarded on stop, quit,
  EOF or session failure. Terminal echo or an external terminal recorder can
  still display/capture typed input. Sent text enters the existing transcript
  and event stream. No draft autosave or resume is provided.
- Input uses a bounded 32-line queue and reads at most 4 KB at a time, pausing
  while the queue is full. Pasting more than 32 short lines does not silently drop
  them. Invalid UTF-8 or an input line over 8,000 characters ends input with an
  error. Ctrl-C drops already buffered input and the draft before stopping work.

The same line-mode behavior applies to NDJSON output and piped/redirected input.
The [interactive screen](CONVERSATION_TUI.md) additionally supports moving among
earlier draft lines, bracketed paste and a scrollable transcript.

## Persistence and recovery

The local adapter derives ownership from the OS user, binds the workspace and
session ID, and uses 0700 storage directories plus 0600, singly linked regular
files. It rejects symlink roots/final files, FIFOs, public permissions, mismatched
owners/workspaces, malformed IDs, oversized input and changed snapshot digests.
Directory-relative I/O stays anchored to the opened storage directory. Trusted
parent directories and same-user filesystem administration remain local trust
assumptions; this is not protection against a malicious process running as you.

A held per-session file lock rejects competing writers. Every transition is
written to a private temporary file, fsynced, atomically replaced, and followed by
a directory fsync. Snapshot digests detect corruption, not adversarial rewriting
by the owner or rollback to an older valid copy. There is no remote backup,
automatic replication, shared catalog, or cross-user aggregate.

The consumed cassette position and `running` state are saved before dispatch.
After a crash, resume changes that state to `interrupted` without retrying it.
A storage failure prevents further dispatch from that controller; reopen to
inspect the durable snapshot. Reopening a session restores no approvals, machine
tools or live-provider credentials. Retained state includes explicit conversation
text, statuses, recorded chat usage and identity/configuration hashes. Explicit
reviews additionally retain their selected packet and structured report in the
same private snapshot.
Current request configuration and limits are reconstructed from installed code.

Storage is user-selected and retention is manual through `session-delete`. The
JSON file contains the current transcript; `.lock` files are synchronization
metadata and must not be removed while a session is open. An abnormal process
exit can leave a private temporary file with transcript content. Version history,
compaction, SQLite indexing and remote adapters remain future work.

## Scope and verification

This is the first recorded conversation milestone in plan §16.0. The plain `mos`
entry point still displays command usage. Live conversation,
live review, repository execution, shared `exec` routing,
and advanced terminal features remain open. The existing MCP and analysis commands are
independent of this preview.

`tests/test_conversation.py` exercises exact contextual follow-ups, fresh-session
separation, queued input, cancellation, explicit continuation, interrupted resume,
save failure before/after a reply, competing writers, ownership/integrity checks,
bounded hostile files, and real subprocess save/resume. The installed-wheel suite
also runs this file from outside the checkout. Validation on 2026-09-09:

- Full quality gate: 745 source tests (three optional integration skips), 88%
  branch-inclusive coverage, strict typing, lint/format, locked export and build.
- Final terminal refinements: all 22 focused conversation tests and strict typing
  passed; the resulting installed wheel passed all 128 smoke tests.
- A real PTY exercised a completed reply, SIGINT, clean quit and durable state.
  All 146 local documentation link targets resolved.

All conversation tests use synthetic inputs and make no provider calls.

The navigation milestone additionally exercises workspace-only metadata, active
session detection, bounded scans, stale/latest-selection races, deletion failure
and temporary-file validation, missing workspace retention, and a real separate
process resuming the latest matching-workspace conversation. Validation on
2026-09-09: all 36 focused conversation tests passed, followed by the full quality
gate with 760 source tests (three optional integration skips), 88% branch-inclusive
coverage, lint/format, strict typing, locked export, build and 142 installed-wheel
smoke tests. A human-output list/delete/empty-list walkthrough and all 146 local
documentation link targets also passed.

The multiline milestone adds coverage for exact code-block context, unsent draft
isolation, literal command text, active-response queueing, empty/oversized/full
session rejection, storage failure, Unicode read boundaries, backpressure,
redirected input and separate-process resume. Validation on 2026-09-09: all 63
focused conversation tests, strict typing and lint passed. A real PTY exercised
an unsent draft, SIGINT discard, a multiline completion and a durable snapshot
without discarded content. The full quality gate passed with 787 source tests
(three optional integration skips), 88% branch-inclusive coverage, lint/format,
strict typing, locked export, build and 169 installed-wheel tests. All 285 local
documentation targets resolved.

The steering milestone exercises automatic and explicit task binding, request
serialization, frozen review boundaries, storage failure, chained unanswered
intent, unavailable steering, stop, composer submission, legacy snapshot encoding
and invalid target/attempt-count rejection. A killed CLI process retains a queued
refinement; a separate resume process stays paused until explicit continuation
and verifies exact request-bound recovery and later context. All 75 focused
conversation tests passed, along with strict typing and lint. A real PTY verified
visible task links, queued steering, serialized completion and durable state.
The full quality gate passed with 799 source tests (three optional integration
skips), 88% branch-inclusive coverage, lint/format, strict typing, locked export,
build and 181 installed-wheel tests. All 287 local documentation targets resolved
(2026-09-09).
