# Recorded conversation preview

`mos chat` now keeps a text conversation across messages and saves it privately.
`mos resume <session-id>` explicitly restores that conversation in the same
workspace. This first milestone uses request-bound recorded responses: it does
not generate arbitrary answers or call a live provider. Every recorded response
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

## Interaction and automation

The preview is a line-oriented terminal with user input, assistant answers, and
visible queued/running/completed/cancelled/interrupted/failed states. The composer
accepts additional lines while a response is active. They enter a bounded queue
and become separate contextual follow-ups after that response. Active-request
steering and a multiline/full-screen composer remain future work.

- `/stop` or Ctrl-C cancels the active request and queued messages, retaining their
  text and status. The session remains open for new input.
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
Each message permits one request, no tools, no retries, and a 30-second timeout.
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
tools or live-provider credentials. The retained state includes only explicit
conversation text, statuses, recorded usage and identity/configuration hashes.
Current request configuration and limits are reconstructed from installed code.

Storage is user-selected and retention is manual. The JSON file contains the
current transcript; `.lock` files are synchronization metadata and must not be
removed while a session is open. An abnormal process exit can leave a private
temporary file with transcript content. Close all handles before deleting a
session's files. Version history, compaction, a local listing/deletion interface,
SQLite indexing and remote adapters remain future work.

## Scope and verification

This is the first recorded conversation milestone in plan §16.0. The plain `mos`
entry point still displays command usage. Live conversation, automatic session
selection, integrated blind review, repository execution, shared `exec` routing,
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
