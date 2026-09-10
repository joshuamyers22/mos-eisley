# User and project memory

Mos now supports explicit personal memory shared across your projects and private
memory for the selected project. New conversations load both enabled scopes.
The terminal header shows the active revisions and working directory; `/memory`
shows or hides the complete context fixed for this session. `/directory` shows
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
commands and new conversations. The selected canonical workspace is currently the
project boundary: launching in a subdirectory creates a different project scope.
Use the same `-C` root consistently. Git-root discovery, project moves and explicit
worktree sharing remain planned; remote repository URLs never merge stores.

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
`--no-memory` skips all memory reads and loading for that launch, including invalid
or unavailable memory storage. It does not erase anything.

Each inspection/update reports the document revision and SHA-256. When editing a
previously inspected version, pass `--expected-sha256 HASH` to reject a stale edit;
use `missing` when creating a document that must not exist yet. Without that flag,
an explicit operation applies to the latest document under the store lock.
`--json` emits one structured receipt, including the selected path and document.

Updates are commands invoked by the user. The model cannot call them as tools.
Natural-language remember/forget, in-session editing, automatic extraction and
proposed-memory approval controls remain planned. Ordinary chat text is not
automatically promoted to either memory scope.

## Session consistency and retention

The effective memory documents and revisions are retained with the private session
snapshot. An existing conversation keeps its original memory context; editing a
memory document cannot modify an already dispatched request. Before each subsequent
turn, Mos checks the current enabled memory against the saved selection. Changes,
clearing, disabling, corruption or unavailable storage pause work before an attempt
is consumed. Adding memory to a session opened without any also requires a fresh
session, unless it was launched explicitly with `--no-memory`.

Resume requires the same active memory selection. If it changed, Mos preserves the
old session and explains that a new session is needed. Start `mos` for current
memory or `mos --no-memory` for a fresh session without it. An old session that never
had memory can be resumed with `--no-memory`. Replacing/removing memory inside an
existing saved conversation is not yet supported: there is no silent refresh,
replay or restoration of forgotten memory. Unchanged memory still supports normal
`mos resume --last`.

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
bounded at 256 KiB, including metadata and escaping. No background memory generation,
network access, credential lookup or cross-user pooling is introduced.

Explicit `conversation-demo` and `conversation-review-demo` now bind their chat
recordings to the selected memory too. Generate and consume them with the same
workspace/memory settings; use `--no-memory` on both commands for a memory-free
fixture. Legacy snapshots without a memory field keep their canonical hashes.
