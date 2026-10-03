# External tmux workspace

Run Mos in a tmux pane to keep the same conversation process running when you
detach your terminal. Other panes can hold a shell, test watcher or server. This
uses the existing conversation UI; embedded terminals remain planned.

## Start and return to a workspace

Install tmux separately with your platform's package manager, and install `mos`
using the [quick start](../README.md#quick-start). From the project directory:

```sh
tmux -L mos-workspace new-session -s mos-workspace
mos chat --name "Project work"
```

`-L mos-workspace` selects a separate server socket so workspace commands do not
target your default tmux server. Choose another socket/session name for a separate
workspace. These commands use your ordinary tmux configuration; Mos does not
modify it or adopt other panes. For tmux's default bindings, press Ctrl-B, release
it, then press the next key:

| Keys | Action |
|---|---|
| Ctrl-B then `%` | Split side by side; start a shell or watcher in the new pane |
| Ctrl-B then `"` | Split top and bottom |
| Ctrl-B then `o` | Switch pane |
| Ctrl-B then `z` | Zoom or restore the selected pane |
| Ctrl-B then `[` | Browse tmux history; `q` leaves copy mode |
| Ctrl-B then `d` | Detach the client, leaving the workspace running |

Return from another terminal on the same host and account:

```sh
tmux -L mos-workspace attach-session -t mos-workspace
```

Reattach to the existing Mos pane rather than running `mos resume` while that
conversation is still open. Mos holds an exclusive saved-session lock. Detachment
preserves the running UI's draft and current work; a draft is still unsaved and is
lost if the Mos process exits. Active live calls may continue and incur spending
while detached. Use Ctrl-C or `/stop` inside Mos when you intend to cancel work.
Tmux's prefix controls the workspace; Mos's keys control the conversation.

Ctrl-D or `/quit` inside Mos closes its UI and saves the conversation. To reopen
that exact conversation after Mos exits, run `mos resume SESSION_ID` from the same
project with the same storage options. `mos resume --last` selects the latest saved
conversation in that workspace. Queued work stays paused until continued.
Live sessions additionally require the [live launch/resume options](CONVERSATION_TUI.md#live-openai-conversation).

Sibling shell commands are user-operated. Mos does not automatically sandbox,
observe, cancel or attribute them, and their output is not model context. Verify
the sibling shell's directory before starting commands. A separate tmux socket
does not provide a security sandbox or protect against other processes running as
your account. Avoid placing credentials in tmux commands or configuration.

## Disconnect, exit and failure

Tmux can preserve processes across client detach or connection loss while its
server and host remain alive. Reattachment reconnects to those processes; it does
not reconstruct a crashed controller. Server loss, Mos failure and host restart
can terminate Mos and discard drafts. Inspect saved state with the existing
session controls before explicitly resuming; never automatically rerun an
uncertain write or paid call. Tmux history is a display aid, not Mos's saved
conversation or verification evidence.

Use Mos's transcript navigation for the full-screen conversation. Tmux copy mode
can show only the terminal history it retains; it may not contain the full Mos
transcript. Resize or zoom panes to give the composer enough space. Use a terminal
that supports bracketed paste; pasted slash commands remain literal messages.
Custom prefix/key bindings, terminal capabilities and tmux configuration can
change behavior; the automated checks below use an empty tmux configuration.

## Compatibility checks and platform evidence

From a checkout with the pinned development environment:

```sh
tmux -V
MOS_REQUIRE_TMUX=1 uv run --frozen python -m unittest discover \
  -s tests -p test_conversation_tmux.py -v
```

The tests create private temporary servers, synthetic recordings and storage.
They do not contact providers or touch the user's tmux server/configuration.
They cover real PTY client attachment, draft/Unicode preservation through
detach/reattach and split/resize/zoom, literal bracketed paste, stop/quit controls,
paused queued-work continuation, rejection of a competing controller and server
loss with explicit storage reopening. Stop during an active request is covered
by the separate conversation UI suite; tmux tests do not claim live-call failure
qualification. `tools/smoke_package.py` runs the same tests from an installed wheel
outside the checkout. Without tmux, local tests explicitly skip; with
`MOS_REQUIRE_TMUX=1`, absence fails. Ubuntu source and package CI require tmux.

Record OS, tmux version, source revision, source/installed-wheel results and
terminal configuration for each qualification. Actual Windows-hosted WSL2
evidence is required separately; Ubuntu CI does not establish WSL2 support.
Native Windows support remains planned under the
[platform release contract](mos-eisley-plan.md#27-windows-platform-release-contract)
and will not require tmux. Ordinary Mos launch on supported platforms remains
available when tmux is absent.

Evidence on 2026-10-02, based on GitHub main `a1cb38b` plus this change:

| Platform/configuration | tmux | Source compatibility suite | Installed-wheel compatibility suite |
|---|---|---|---|
| macOS 15.1, private server with empty config, PTY client using `xterm-256color` | 3.7c | 4 passed | 4 passed |
| Ubuntu GitHub CI | Recorded by each run | Required; not yet run for this change | Required; not yet run for this change |
| Actual Windows-hosted WSL2 | Pending | Pending | Pending |

The macOS result covers the synthetic automated terminal setup, not every terminal
application or custom tmux configuration. This table does not qualify the deferred
embedded terminal backend or native Windows support.

References: [tmux manual](https://man.openbsd.org/tmux) and
[getting started](https://github.com/tmux/tmux/wiki/Getting-Started). Check options
against your installed release.
