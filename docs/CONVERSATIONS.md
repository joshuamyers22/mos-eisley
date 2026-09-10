# Recorded conversation preview

`mos chat` now keeps a text conversation across messages and saves it privately.
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
Resume requires the same canonical workspace and exact cassette. A new `chat`
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
snapshots and 8 MB of aggregate snapshot input (2 MB per snapshot). Invalid or
over-limit catalogs fail instead of returning a partial selection. Retained lock
files count toward the directory limit. Use a dedicated private storage directory;
pagination and cleanup of unused lock files remain future work.

## Interaction and automation

The preview is a line-oriented terminal with user input, assistant answers, and
visible queued/running/completed/cancelled/interrupted/failed states. The composer
accepts additional lines while a response is active. They enter a bounded queue
and become separate contextual follow-ups after that response. Active-request
steering and a multiline/full-screen composer remain future work.

- `/stop` or Ctrl-C cancels the active request and queued messages, retaining their
  text and status. The session remains open for new input.
- `/review` or `Review this change.` runs a configured explicit recorded review
  packet and returns a bounded summary. See the
  [review workflow](CONVERSATION_REVIEW.md) for setup, isolation and evidence limits.
- `/quit` cancels active work, saves queued messages without executing them, and
  exits. On resume, `/continue` or a new message explicitly starts queued work.
- EOF finishes work already enabled in this invocation, then exits. Opening a
  resumed session followed by EOF only displays/saves it; it does not execute its
  pending messages. Ctrl-C remains effective while finishing work after EOF.
- `--json` emits NDJSON lifecycle events using the same controller. Input is still
  one plain-text message or command per line. Pipes, redirected files and terminals
  are supported. Control characters are escaped in terminal output.

There are at most 16 submitted messages per session and 8,000 characters per
message/answer. The existing agent request and response byte budgets still apply.
Each ordinary chat message permits one request, no tools, no retries, and a
30-second timeout. Explicit reviews use their separately bounded critic/judge
workflow and do not consume a chat cassette position.
Failed/cancelled/interrupted messages remain visible but are excluded from future
model context. Completed messages include recorded usage; failed attempts retain
their consumed cassette position without inventing usage. A failed recorded
request pauses dispatch and emits an error; the session itself remains usable.
Unexpected text cannot match this synthetic demo's exact request hashes.

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
and the full terminal UI remain open. The existing MCP and analysis commands are
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
