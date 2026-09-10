# Interactive terminal conversation

Mos Eisley's primary interface is an ongoing terminal conversation. Bare `mos`,
`mos chat` and `mos resume` open a full-screen transcript and editable composer when
both input and output are terminals. This is the first implementation of the
terminal interaction requested in plan §16.0, with Codex and Claude Code as the
interaction references. It uses recorded responses; arbitrary live answers,
repository tools and provider/model switching are not enabled by this screen.

## Start a conversation

Open your project directory and run:

```sh
mos
```

Type `Remember that the fixture boundary is ten.` and press Enter. After the
answer, type `What boundary did I give you?` and press Enter. The second answer
uses the first exchange. Ctrl-D exits; the normal terminal returns with the saved
session ID. Resume from the same project directory:

```sh
mos resume --last
```

Saved queued messages remain paused until F4, `/continue`, or a new submitted
message explicitly continues them. Opening the screen and editing a draft do
not start work. Each bare `mos` or `mos chat` starts an empty conversation.

`mos -C /path/to/project` selects another workspace without changing your shell's
directory. The welcome screen shows the canonical workspace, session ID and the
two supported preview messages. Session files use `~/.mos-eisley-sessions` by
default, created privately on the first new session. `mos sessions` lists only
your current workspace's sessions. `mos resume SESSION_ID` selects one explicitly.
The existing owner, permissions, locking and workspace checks apply to default
storage too; an unsafe existing directory is rejected, never repaired silently.

Use `--storage /private/path` to select another location; its parent must exist.
`--session-max-bytes BYTES` on launch or resume saves a per-session snapshot budget;
the welcome screen shows it and `mos sessions` reports usage. See
[storage budgets](CONVERSATION_STORAGE.md) for bounds and the expansion plan.
`--storage-backend sqlite` uses the [incremental SQLite backend](CONVERSATION_SQLITE.md)
through the same terminal controller. Repeat the backend option when resuming.
Use `--cassette /path/to/recording.json` for a custom recording, passing the same
recording and storage when resuming. After an explicit memory refresh, the retained
replacement recording is used unless you supply a cassette. Missing, invalid or mismatched recordings
fail; they never fall back to the built-in preview. The built-in recording is
request-bound too, so arbitrary prompts cannot receive live answers. No setup
files, credentials or network connections are needed to open the default preview.

`--plain` keeps the line-oriented interface. Pipes, redirected input, and `--json`
also use that interface automatically. `--tui` explicitly requires terminal
input/output and rejects `--json` before creating storage. Bare launches with piped
input use the same saved line-mode conversation. `mos --help` and `mos --version`
remain informational; unknown commands still fail instead of becoming prompts.
Launch options may follow `mos` directly; use `mos chat --help` for their full list.

The startup reference is [Codex's documented project-directory launch](https://learn.chatgpt.com/docs/codex/cli),
checked 2026-09-09. Mos now matches the no-subcommand terminal entry point. Live
authentication, an initial positional prompt and an interactive resume picker
remain future work; this is not complete Codex feature parity.

The persistent header now shows the working directory and active user/project memory
revisions. `/directory` shows the full path, and `/memory` toggles complete memory
details in the scrollable transcript. See [memory management](CONVERSATION_MEMORY.md)
for explicit saves, scope selection, no-memory launches and changed-memory recovery.
`/memory refresh` applies current saved memory between requests; `/memory off`
disables it for this session. Both save the selection and pause queued work until
F4, `/continue`, or a newly submitted message continues it.

## Keyboard controls

| Control | Action |
| --- | --- |
| Enter | Send the current message; a typed slash command invokes its control. |
| Alt-Enter or Ctrl-J | Insert a newline without sending. |
| Arrow keys, Home, End, Backspace | Edit the multiline draft, including earlier lines. |
| Ctrl-S | Send literal text, including a leading slash. |
| Ctrl-U | Discard the unsent draft and its undo history. |
| Ctrl-C | Discard the draft and stop active work and queued messages. |
| Ctrl-D | Discard the draft, cancel active work, retain queued messages and exit. |
| Tab | Switch focus between the transcript and composer. |
| Page Up / Page Down | Focus and scroll the transcript; Tab returns to editing. |
| F3 | Expand/collapse the latest review's findings and evidence. |
| F4 | Explicitly continue saved or paused queued work. |
| F5 | In SQLite sessions, browse saved history or return to the live view. |
| F6 | Reload saved history from its first page after a change or read error. |
| F7 | Select the next memory or review reference on the saved history page. |
| F8 | Open/close the selected artifact; only one stays expanded. |

## Saved SQLite history

SQLite's live transcript shows the four most recent messages. Press F5 to browse
earlier saved messages, four per page, using the verified
[transcript reader](CONVERSATION_SQLITE.md#transcript-pages). Page Up/Page Down
scroll within the current page; pressing again at its top/bottom loads the previous/
next page. Arrow keys also scroll within the page. F5 returns to the live view and
composer, preserving the unsent draft. Tab allows editing while browsing.

The browser retains one page of text plus visited cursors. It reads in a background
thread, with one page/artifact read in flight and at most one pending replacement; repeated key presses
do not accumulate threads or pages. Results from a closed or replaced view are
discarded. History reads and saves from the same terminal share a guard so the
background reader cannot cause its own save to fail with a busy-database error.
A save waits for an active read to finish. Quit stops the terminal worker, clears the draft, and joins an in-flight
read before completing cleanup. Storage reads have bounded inputs but no separate
wall-clock timeout; slow filesystem I/O can delay saves and final exit. Other
processes retain the backend's existing busy/failure behavior.

Browsing never saves a session, consumes a recorded attempt, or continues queued
work. If the session changes while browsing, the old page clears and F6 reloads it.
Changes in another session can invalidate the cursor on the next page read. Missing,
corrupt or inaccessible records show an error without falling back to an unchecked
copy from controller memory. Memory and review artifacts initially appear as
references. F7 cycles the selection; F8 explicitly opens or closes its verified
JSON content. Nothing expands automatically. Expansion reads at most 512,000 stored
artifact bytes after checking the reference, owner, workspace and snapshot. Larger
artifacts show their required size; use the [artifact CLI](CONVERSATION_SQLITE.md#selected-artifacts)
with an explicit larger budget to inspect them. The terminal retains one expanded
artifact, clearing it when the selection, page, session or view changes. Stale
selections require F6 reload. Artifact reads use the same serialized background
worker and read/save guard as pages; switching selection discards obsolete results.
Content is escaped for terminal display and is never sent to a model or critic.
F3 review details are available after returning to live view. `/memory` and
`/directory` inspection also return to live view to show current session information.

Older SQLite indexes may require explicit preparation. Exit the active session,
follow the reader's `session-transcript --prepare --expected-sha256 HASH` instructions,
then resume and press F5. Paging never prepares an index automatically. JSON snapshot
sessions keep their existing transcript view; F5 explains that paging requires SQLite.
The controller still reconstructs the full bounded state on resume/save. This is
bounded display navigation, with the 16-message preview cap still in place; bounded
controller loading and context management remain planned.

## Input behavior

Typing `/review`, `/steer TEXT`, `/stop`, `/continue`, or `/quit` and pressing
Enter uses the existing conversation controls. `/context` toggles a read-only
preview of the next queued chat's selected history, steering ancestry, omissions
and context-byte usage. It returns from saved history to live view, does not enable
paused work, and marks the report stale after the session revision changes. See the
[context preview contract](CONVERSATION_STORAGE.md#context-selection-preview).
The line-mode `/compose`, `/send`
and `/discard` commands are unnecessary here; use the editor controls above.

Bracketed paste inserts the whole pasted block without executing it. It stays
literal when sent, even if it contains `/quit` or `/review`. Ordinary typed
`Review this change.` still requests the selected review packet. Multiline
messages and Ctrl-S submissions remain literal. Terminals that do not frame
pasted text cannot distinguish its newline keystrokes from typed Enter; use a
terminal with bracketed-paste support for this workflow.

For a request-bound code-block example, generate `conversation-demo --multiline`
and send the exact multiline prompt documented in
[Multiline composition](CONVERSATIONS.md#multiline-composition), without the
line-mode `/compose` and `/send` controls. Edit or paste the code block in the
composer, then press Enter once.

## During work

The composer remains usable while a response or review runs. Sent chat input
retains the existing [steering link](CONVERSATIONS.md#steering-during-work) to the
active task and queues at the next request boundary. The transcript shows each
message's status and refinement target. Scrolling the transcript preserves its
position when progress arrives; returning to the composer follows new output.

The persistent status bar shows the fixed fixture model and effort, tools-off
state, current activity, pending-message count, consumed cassette attempts, and
recorded byte usage. Configured launches also show current queued UTF-8 text bytes
against the [pending text budget](CONVERSATION_STORAGE.md#pending-text-budget).
Rejected message drafts remain in the editor. Recorded bytes are fixture usage,
not live token or dollar accounting. This version shows complete answers and
lifecycle progress; it does not stream provider tokens.

F3 expands up to ten adjudicated findings from the latest completed review,
including quoted evidence. The full structured report remains in the same saved
session. Review packets, critic isolation and review deadlines are unchanged;
see [Conversation review](CONVERSATION_REVIEW.md).

## Drafts, bounds and recovery

Drafts allow 8,000 characters and 256 lines. An oversized edit is rejected as a
whole and prevents sending until Ctrl-U clears the draft, so a truncated paste
cannot be submitted accidentally. Undo/redo retains at most 32 edit snapshots.
There is no persistent input history, draft autosave, external-editor launch,
shell shortcut, or automatic repository scan.

Ordinary text, natural-language reviews, and typed `/steer TEXT` and `/review`
submissions clear the editor only after the shared terminal confirms durable queue
admission. Rejection for a full session, pending-text budget, missing review packet
or unavailable steering leaves the exact submission editable. These commands use
the same controller validation as line input; accepted steering retains its link
to the active chat. Pasted/multiline text and explicit literal submissions keep
their existing literal behavior. Other slash controls clear when handed to the
input queue and report any unavailable operation in the notice area.
Stop and quit take priority over pending editor handoffs, and cancelled handoffs
cannot later dispatch. A full input queue retains an unsent message or command.
Fatal storage/UI failure closes the screen and discards its unsaved draft;
durable messages retain the existing snapshot recovery rules.

Transcript control sequences and bidirectional formatting controls display as
escaped text. The UI does not interpret model output as terminal commands or
markup. The application restores terminal modes and exits the alternate screen
on normal exit and handled failures. A process killed without cleanup can still
require the terminal's normal reset procedure; its unsent draft is not saved.

## Implementation and validation

The screen uses [prompt-toolkit's application/layout interface](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/full_screen_apps.html)
with a bounded editor and in-memory undo history. Typed submissions go through
the same `terminal()` orchestration and `ConversationController` as line/JSON
input. The renderer adds no provider, review, storage or tool authority.
The new dependency and its width helper are pinned in the lock and hash-checked
runtime export; no existing dependency version was changed.

The tests use [pipe input and dummy output](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/unit_testing.html)
for real key handling, plus a real subprocess PTY for automatic screen selection,
a recorded reply, alternate-screen exit and terminal-mode restoration. They also
cover multiline editing, paste/command separation, input bounds, review expansion,
queued steering, stop/quit, paused resume, storage failure and cancelled handoffs.
The same test file runs from the installed wheel outside the checkout.

Validation on 2026-09-09: all 17 UI tests passed, including a real PTY, and the
runtime dependency audit found no known vulnerabilities or adverse project
statuses in 50 packages. All 296 local documentation targets resolved.
The full quality gate passed with 816 source tests (three optional integration
skips), 88% branch-inclusive coverage, lint/format, strict typing, locked export,
build and 198 installed-wheel tests. No live provider calls were used for this
milestone.
