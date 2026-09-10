# Interactive terminal conversation

Mos Eisley's primary interface is an ongoing terminal conversation. `mos chat`
and `mos resume` now open a full-screen transcript and editable composer when
both input and output are terminals. This is the first implementation of the
terminal interaction requested in plan §16.0, with Codex and Claude Code as the
interaction references. It uses recorded responses; arbitrary live answers,
repository tools and provider/model switching are not enabled by this screen.

## Start a conversation

Use new output names and a private storage directory whose parent already exists:

```sh
mos conversation-demo --output /tmp/mos-screen-cassette.json
mos chat --cassette /tmp/mos-screen-cassette.json --storage /tmp/mos-screen-sessions
```

Type `Remember that the fixture boundary is ten.` and press Enter. After the
answer, type `What boundary did I give you?` and press Enter. The second answer
uses the first exchange. Ctrl-D exits; the normal terminal returns with the saved
session ID. Resume explicitly with the same workspace and cassette:

```sh
mos resume --last --cassette /tmp/mos-screen-cassette.json --storage /tmp/mos-screen-sessions
```

Saved queued messages remain paused until F4, `/continue`, or a new submitted
message explicitly continues them. Opening the screen and editing a draft do
not start work. A fresh `chat` starts with an empty conversation.

`--plain` keeps the line-oriented interface. Pipes, redirected input, and `--json`
also use that interface automatically. `--tui` explicitly requires terminal
input/output and rejects `--json` before creating storage. The bare `mos` command
still shows command help: this preview requires an explicit cassette and storage
selection rather than inventing a live provider configuration.

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

Typing `/review`, `/steer TEXT`, `/stop`, `/continue`, or `/quit` and pressing
Enter uses the existing conversation controls. The line-mode `/compose`, `/send`
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
recorded byte usage. Those bytes are fixture usage, not live token or dollar
accounting. This version shows complete answers and lifecycle progress; it does
not stream provider tokens.

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

Ordinary text and natural-language review submissions clear the editor only
after the shared terminal confirms durable queue admission; rejected messages
remain editable. Typed slash controls clear when handed to the input queue and
report any unavailable operation in the notice area.
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
