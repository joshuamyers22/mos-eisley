# Choose a session directory

Open a directory selector before starting a conversation:

```sh
mos --choose-directory
mos chat --choose-directory --name "Parser cleanup"
mos resume --choose-directory
```

For resume, choose the workspace first, then choose a saved session in the resume
picker. You can also combine the directory selector with a session ID, `--last`,
or `--name NAME`. Repeat `--storage-backend sqlite` when using SQLite sessions.

| Control | Action |
| --- | --- |
| Type, arrows, Home/End, Backspace | Edit the directory path. |
| Tab | Show directory completions; further presses cycle through them. |
| Enter | Validate the path and preview its canonical target. |
| Ctrl-S | Use the previewed directory. |
| F2 | Focus the scrollable path preview or return to editing. |
| Ctrl-U | Clear the path. |
| Escape / Ctrl-C / Ctrl-D | Cancel startup. |

The initial field contains the shell's working directory, or the value supplied by
`-C PATH`. Relative paths are resolved from the shell's original working directory;
`~` expands to the user's home. Symlinks resolve to the canonical target shown in
the preview. Spaces are preserved, so enter paths containing spaces directly
without shell quotes. Editing the field clears the selection and requires another
preview. Selecting checks that the previewed directory still exists with the same
identity; a changed or missing directory requires a new preview.
For a long target, press F2 and use arrows or Home/End to inspect the full path.
The preview also shows the detected Git-marker root and the project-memory identity.
With `--memory-project-root PATH`, it previews that explicit ancestor identity and
requires a workspace within it.

The selector runs before session lookup, memory loading or session creation.
Cancelling creates no session or memory files. New chats load the selected
workspace's project memory plus enabled user memory. Resume retains the existing
owner/workspace and memory checks; it leaves queued work paused. The selected
canonical directory appears in the conversation header, with `/directory` showing
the full path. Directory identity is rechecked during startup before memory loading
and before opening session storage.

The selector requires terminal input and output. Pipes, `--json`, `--plain`, and
`--inspect` use `-C PATH` instead. Bare `mos` continues to use the shell's current
directory; the selector is opt-in. It does not change the shell or process working
directory, so other relative options such as `--storage` and `--cassette` retain
their usual interpretation. An explicit initial prompt is submitted after the
directory has been selected and the new session opened.

## Switch during a conversation

In the interactive terminal, press F9 or type `/directory switch` to choose another
directory. `/directory switch PATH` selects an existing path directly. Relative
paths in either flow start from the current session workspace; `~` still expands
to the user's home. Enter paths containing spaces directly, without shell quotes.
`/directory` on its own continues to inspect the current workspace.

Active work blocks switching. Let it finish or explicitly stop it first; the
existing `/stop` action cancels active and queued work. Send or discard an unsent
draft before using F9. Pending editor submissions or input also block a switch.
While the picker is open, the current session remains open and locked, with work
paused. Cancelling returns to the same controller and saved state. Choosing the
current directory is a no-op. Invalid selections leave the current session open.

After selection, the old session closes and its saved ID is printed. A fresh
session opens in the selected directory. Previous messages and queued work remain
in the old session and can be resumed by its ID or name. They are not transferred
to the new project. The new conversation loads that project's current enabled
memory plus user memory through ordinary startup validation. A previous explicit
`--memory-project-root` selection is cleared during the switch.

The new session uses the built-in recorded preview and starts unnamed with no
messages. Its initial launch prompt, old recording, review packet, memory-refresh
arguments and latest/name lookup are cleared. The invocation's storage location,
backend, memory-storage location, explicit `--no-memory` choice, and budget options
remain selected. A session-local `/memory off` affects the old session; fresh
startup follows the invocation's memory option. Custom recordings and review
packets can be selected again through a separate launch with their explicit flags.

Wait for the new workspace header before typing. Editing is paused during the
handoff; pending terminal keystrokes are cleared and a fresh input parser is used
for the new screen. Pasted or multiline switch-looking text, Ctrl-S literal
submissions, and initial prompts remain messages. Plain/JSON sessions do not switch
in place; launch another conversation with `-C PATH`.

The selected directory is checked again before destination startup. If it changes
or startup fails, the old session remains saved under its printed ID. Resume it
with the same workspace/storage/backend and any required custom recording; no
different session or project is silently substituted.

## Project-root visibility

The terminal header shows the working directory and a separate project-root line.
`/directory` shows both full paths, the discovery result, and the effective project
memory identity. Plain startup output includes the same information. JSON
`conversation.opened` and `conversation.directory` events include `workspace`,
`project_root` (a path or null), `project_detection`, and `memory_workspace`.

Discovery checks the canonical workspace and its ancestors for the nearest `.git`
directory or regular file. A file marker keeps a linked worktree or submodule rooted
at that marker's parent; its pointer is never followed to a shared metadata directory.
Nested markers take precedence. These are candidate roots identified by metadata:
the application does not validate repository contents, read marker/configuration
files, run Git, or apply Git environment overrides. Bare repositories without a
`.git` marker are outside this discovery flow.

The scan checks at most 64 directories, including the workspace. `project_detection`
is `git-directory`, `git-file`, `none`, `unavailable`, or `limit`. `none` means the
filesystem root was reached without a marker. Symlink or special-file markers,
read errors, and the scan limit leave the root unknown; an obstructing inner marker
does not select an outer repository. Discovery errors provide fixed guidance without
OS diagnostics. The metadata bound is not a timeout for a slow mounted filesystem.

Each preview scans when Enter is pressed. Each opened conversation takes one
discovery snapshot, used consistently by its header and `/directory`; redraws do
not scan the filesystem. A fresh launch, resume, or directory switch discovers
again. Changes to markers while a conversation is open do not retarget its display
snapshot or saved identity.

Project memory defaults to the selected canonical workspace. New sessions can
[explicitly select an ancestor memory identity](CONVERSATION_MEMORY_PROJECT.md),
which is then retained on resume. Saved-session lookup stays workspace-scoped.
Root discovery itself supplies display metadata and never selects memory or tool
authority. Automated migration, collision handling and project/worktree mappings
remain planned in §16.0.2.

## Bounds and remaining work

Path input is one printable line of at most 4,096 UTF-8 bytes. Invalid or oversized
edits are rejected without echoing their content in diagnostics. The editor keeps
at most 32 undo entries and has no persistent input history. Completion reads
immediate directory metadata only when requested with Tab; it scans at most 1,024
entries and offers at most 100 matching directories. Exceeding either limit returns
no partial completion list; type the path directly. File contents are not opened.
These are entry and byte bounds, not a timeout for a slow mounted filesystem.

Directory selection supplies session context and does not grant filesystem tools
or load repository configuration. The recorded terminal's existing execution
limits apply. Workspace persistence still uses the canonical path; the startup
identity check does not add a durable inode binding or filesystem sandbox.
Git-marker root visibility and explicit memory-root selection are available;
automated memory migration and project identity mapping remain planned.
