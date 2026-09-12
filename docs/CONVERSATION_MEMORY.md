# User and project memory

Mos now supports explicit personal memory shared across your projects and private
memory for the selected project. New conversations load both enabled scopes.
The terminal header shows the active revisions and working directory; `/memory`
shows or hides the complete currently selected context. `/directory` shows
the full canonical path. Neither inspection command sends a model request.

## Save and inspect

From your project directory:

```sh
mos memory append --scope user --text "Prefer concise explanations with examples."
mos memory append --scope project --text "Run tests with make check."
mos memory show --scope user
mos memory show --scope project
mos
```

`--scope` is always explicit. User memory applies to your other project sessions;
project memory does not. `-C /path/to/project` selects the project for both memory
commands and new conversations. By default the canonical workspace is the project
boundary: launching in a subdirectory creates a different scope. New chats can
explicitly select an ancestor with [`--memory-project-root PATH`](CONVERSATION_MEMORY_PROJECT.md).
The saved identity is reused on resume and refresh. Use `memory-project-preview`
to compare existing documents first; reviewed migration and
[explicit project/worktree mappings](CONVERSATION_MEMORY_MAPPINGS.md) are available. Git discovery and remote URLs never merge stores. `/directory` shows
the effective memory identity separately from the detected Git-marker root.

The runtime includes memory as labelled user/project context. Project preferences
override general user defaults, and current user instructions override both.
Memory does not grant tools, approvals, credentials or spending authority. The
recorded preview still answers only its two prescribed prompts: inclusion in the
request is implemented, but these fixed answers do not demonstrate a live model
applying arbitrary remembered preferences. Independent review requests still use
only their explicit packets; they do not receive this ambient memory.

## Edit, disable and clear

Replace a scope with Markdown from a bounded, regular UTF-8 file:

```sh
mos memory set --scope project --text-file /path/to/project-notes.md
mos memory disable --scope project
mos memory enable --scope project
mos memory clear --scope project
mos --no-memory
```

`set` replaces that scope's text; `append` adds a paragraph. Both accept `--text`
or `--text-file`. `disable` retains text while preventing new inclusion; `enable`
restores it. `clear` removes current text and retains an empty revision marker.
Setting or appending text does not implicitly re-enable a disabled scope.
Starting with `--no-memory` skips all memory reads, including invalid or unavailable
storage, and saves that session's disabled selection. It does not erase anything.

Each inspection/update reports the document revision and SHA-256. When editing a
previously inspected version, pass `--expected-sha256 HASH` to reject a stale edit;
use `missing` when creating a document that must not exist yet. Without that flag,
an explicit operation applies to the latest document under the store lock.
`--json` emits one structured receipt, including the selected path and document.

Updates are commands invoked by the user. The model cannot call them as tools.
Natural-language remember/forget, automatic extraction and proposed-memory
approval controls remain planned. Ordinary chat text is not
automatically promoted to either memory scope.

## Edit from a terminal session

Both the full-screen terminal and plain/JSON mode accept explicitly scoped commands:

```text
/memory show user
/memory append project Run make check before publishing.
/memory set user Prefer concise explanations.
/memory disable project
/memory enable project
/memory clear project
/memory refresh
/continue
```

`show` reads the saved document, including disabled or empty documents; `/memory`
still displays the session's active selection. Every management command requires
`user` or `project`. `append` and `set` require nonempty text; use `clear` to empty a
scope. These commands apply to the latest document under the existing store lock,
like CLI edits without `--expected-sha256`. Use the standalone CLI with that option
when an edit must match a previously inspected revision. Text after the scope is
literal: shell syntax and quote marks are saved as text. Commands accept one line
within the terminal's 8,000-character input limit; use the file-based CLI for larger
or multiline edits. Existing 32-KiB document bounds still apply.

Stop or finish active requests before managing memory. Inspection and attempted
edits pause queued work, including rejected edits. A successful edit reports the
scope, path, revision, enabled state and digest. The project target is the session's
retained memory identity, including an explicitly selected root or saved mapping.

An edit changes the saved document; it does not change this session's selection,
consumed recording exchanges or historical context. Use `/memory refresh` to load
the new selection, then `/continue` for queued messages. Refresh may reject a
combined memory/context/storage limit or require a custom recording replacement;
the saved edit still exists. A session with memory off stays off until explicitly
refreshed. Saving does not implicitly enable a disabled document. Storage failures
may occur after publication, so inspect the saved scope before retrying an append.

Only directly entered commands use this path. Full-screen pasted text and composed
messages remain literal chat input; model/tool output and ordinary remember/forget
phrases never invoke storage edits. Plain input treats each command line as an
explicit command; use `/compose` when supplying literal slash-prefixed chat text.

## Session consistency and retention

The effective memory documents and revisions are retained with the private session
snapshot. Before each subsequent turn, Mos checks current enabled memory against
the saved selection. Changes, clearing, disabling, corruption or unavailable storage
pause work before an attempt is consumed. Sessions with memory explicitly off skip
these reads, including on later resumes.

After editing memory in another terminal, stop or finish active work, then use:

```text
/memory refresh
/memory
/continue
```

`/memory refresh` loads both currently enabled scopes. `/memory off` disables memory
for this session without reading the memory store. Either transition saves the
selection and leaves queued messages paused until `/continue`; it sends no request
and consumes no recorded exchange. Refresh can re-enable a session started with
`--no-memory`. Neither command changes the source memory documents.

Unchanged memory supports normal `mos resume --last`. To explicitly accept a new
selection or disable memory when reopening a saved session:

```sh
mos resume --last --refresh-memory
mos resume --last --refresh-memory --no-memory
```

Without explicit refresh, a changed selection prevents resume. Earlier messages
retain their historical memory context in the private snapshot. That historical
memory is not inserted into future requests, although previous conversation text
and answers may still contain earlier information. Refresh does not erase history
or replay earlier requests.

The built-in recording replaces only unused exchanges. Custom recordings require
an explicit replacement that preserves every consumed exchange exactly:

```sh
mos resume --last --cassette current.json --refresh-memory --refresh-cassette next.json
```

`next.json` must contain the unchanged consumed prefix followed by requests bound to
the newly selected memory and expected conversation history. Regenerating the entire
recording with new memory changes that prefix and is rejected. After a successful
refresh, Mos retains the replacement privately with the session, so later resumes
need no cassette path. In-session refresh of a custom recording explains this
requirement; use the resume command to supply its replacement.

Clearing the current document does not remove copies from older saved sessions,
previous provider requests, filesystem journals or backups. Use the existing
session listing and exact-snapshot deletion controls to remove local saved copies.
The first release has no memory history index, backup eraser or remote sync.

## Storage and bounds

The default directory is `~/.mos-eisley-memory`. `--memory-storage PATH` selects a
different root; use the same override for management, cassette generation, chat and
resume. Its parent must exist. Reading a missing root returns no memory and does
not create it. First write creates a private directory and store lock. An existing
root without its initialized lock is rejected rather than treated as empty.

`user.json` and `project-<canonical-workspace-sha256>.json` contain versioned records
with Markdown text, owner, scope, project identity, source, revision, UTC timestamp,
enabled state and integrity digest. Use the CLI to edit/import text so metadata and
digests remain consistent. Files are private to their OS owner (0600 in a 0700
directory), even for project memory; no project file or Git commit is created.

Regular-file checks reject public files, final-component symlinks, hardlinks and
special files. Reads are bounded; shared/exclusive file locks and atomic replacement
coordinate cooperating processes. Same-user hostile filesystem rewrites/rollback
and untrusted parent-directory replacement are outside this local integrity model.

Each document is capped at 32 KiB of UTF-8 text. Loading additionally caps the
combined user/project text and its serialized request context at 32 KiB; escaped
characters may use more bytes. No truncation occurs. Individually valid documents
can exceed the combined limit; shorten/disable a scope, or use `--no-memory` while
correcting it. Normal request/history budgets still apply. Serialized records are
bounded at 256 KiB, including metadata and escaping. Retained historical context and
recordings must fit the session's saved snapshot budget (2 MB by default; see
[storage controls](CONVERSATION_STORAGE.md)); oversized saves fail
without publishing the new selection. No background memory generation,
network access, credential lookup or cross-user pooling is introduced.

Explicit `conversation-demo` and `conversation-review-demo` now bind their chat
recordings to the selected memory too. Generate and consume them with the same
workspace/memory settings; use `--no-memory` on both commands for a memory-free
fixture. Legacy snapshots without a memory field keep their canonical hashes.
