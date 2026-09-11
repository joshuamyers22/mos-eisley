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
Git project-root discovery and in-session directory switching remain planned.
Switching will need an explicit handoff for active work and unsent drafts before
opening a fresh session with another project's context.
