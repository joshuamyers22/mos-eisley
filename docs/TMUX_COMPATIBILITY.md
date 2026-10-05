# External tmux workspace

Run the existing Mos conversation in a user-operated tmux pane alongside a shell,
test watcher or server. Detach and reattach to the same running Mos process while
keeping its composer draft and queued work. Mos does not start tmux, create sibling
panes, change your tmux configuration or observe commands in other panes.

This implements the documentation and local compatibility slice in
[plan §16.0.5](mos-eisley-plan.md#1605-optional-external-tmux-workspace).
It is separate from the future embedded terminal and optional tmux backend.
The current conversation remains a recorded-provider preview; tmux does not enable
live answers, repository tools or new execution permissions.

## Start and arrange the workspace

Install tmux separately and make an installed `mos` available on PATH. From your
project directory, start a fresh user-operated server with tmux's default bindings:

```sh
tmux -V
tmux -L mos-work -f /dev/null new-session -s mos-work -c "$PWD"
```

The named server keeps this example separate from your usual tmux server, and
`-f /dev/null` avoids loading custom configuration. It does not edit any config
file. If this named session already exists, attach to it instead of starting a
second session. You may use an existing tmux workspace and your own bindings;
the qualification below covers the default bindings with no configuration file.

In the new shell, start Mos:

```sh
mos
```

The Mos header identifies the canonical workspace and session ID. Check these
before sending a message. With the default recorded preview, try `Remember that
the fixture boundary is ten.` followed by `What boundary did I give you?`.
See the [terminal guide](CONVERSATION_TUI.md) for storage, memory and cassette options.

Press Ctrl-b, then `%` to create a shell beside Mos, or Ctrl-b, then `"` for a
shell below it. To select the current pane's directory explicitly when splitting,
press Ctrl-b, then `:` and enter:

```text
split-window -h -c "#{pane_current_path}"
```

Start any watcher or server yourself in that shell. Those processes and their
output remain user-operated: they are not Mos tool calls, sandboxed by Mos or
verification evidence merely because they occupy a sibling pane. Attach selected
output explicitly through a supported Mos input path when needed.

| Action | Default tmux control |
|---|---|
| Switch panes | Ctrl-b, then an arrow key |
| Zoom/unzoom the selected pane | Ctrl-b, then `z` |
| Resize a pane | Ctrl-b, then Ctrl-arrow |
| Detach the client | Ctrl-b, then `d` |
| Enter tmux copy/history mode | Ctrl-b, then `[`; `q` exits default copy mode |

Use Mos's Tab and PgUp/PgDn to navigate its conversation transcript. Tmux copy
mode is a separate view of terminal history, not Mos's saved conversation store.
Prefer a zoomed pane when the composer or header becomes cramped.

## Detach, reattach and stop

Detaching closes the tmux client while the server and Mos process keep running.
From a terminal outside that session, reattach using the same server name:

```sh
tmux -L mos-work attach-session -t mos-work
```

An unsent composer draft survives because the same Mos process is still running;
it is not autosaved to conversation storage. Already-enabled work may continue
while detached. Saved queued work that was paused on resume stays paused until
an explicit continuation; attaching a tmux client does not continue it.

While Mos is running, reattach to its pane. Do not start `mos resume` for the same
saved session in another pane: the existing exclusive controller lock rejects a
competing writer, including while detached.

Inside Mos, Ctrl-C stops active/queued work through its existing controller.
Ctrl-D or typed `/quit` saves and exits Mos, returning to the pane's shell. These
actions are different from detaching tmux. Quit Mos before intentionally closing
its pane if you want a normal save and terminal cleanup.

If the tmux server is lost, Mos is no longer available through that server and
unsaved drafts may be lost. Once the original controller has exited, explicitly
resume the durable conversation from the original workspace:

```sh
mos resume SESSION_ID
```

Use the saved session ID and the same custom storage/backend/cassette options, if
selected. `mos resume --last` is convenient when the latest session is the intended
one. Resume uses Mos's existing recovery rules; it does not reconstruct a tmux
pane, recover unsaved editor text or automatically repeat uncertain operations.
Machine restart and controller failure require the same durable recovery path.

Bracketed paste inserts text into the composer without executing pasted newline
or slash controls. Inspect it before sending; Ctrl-S explicitly submits literal
text. If a terminal or custom tmux paste binding does not frame bracketed paste,
its newlines may act like typed Enter. Do not use unframed paste for command-like
text. The smoke check exercises tmux's `paste-buffer -p` framing.

## Qualification and reproduction

The executable compatibility check is [tools/smoke_tmux.py](../tools/smoke_tmux.py).
It uses fresh synthetic sessions, a private temporary socket, no tmux configuration,
real attached PTY clients and an installed wheel outside the source tree. It starts
only its own test panes and cleans up only its own server. No provider calls or
user-session reads occur. Its final JSON report contains platform/version and
check names, not conversation contents.

Build and install a fresh wheel into a separate environment, then run the check:

```sh
uv run --frozen python -m hatchling build
uv venv /tmp/mos-tmux-check --python 3.12
uv pip install --python /tmp/mos-tmux-check/bin/python --require-hashes -r requirements.runtime.txt
uv pip install --python /tmp/mos-tmux-check/bin/python --no-deps dist/mos_eisley-0.1.0-py3-none-any.whl
/tmp/mos-tmux-check/bin/python tools/smoke_tmux.py --mos /tmp/mos-tmux-check/bin/mos --python /tmp/mos-tmux-check/bin/python
```

Use a fresh environment path for each qualification. The check requires local
socket and PTY access; a runner that denies those operations cannot qualify tmux
compatibility. Missing tmux is an explicit check failure, not a claim that ordinary
Mos requires tmux. The script also exercises ordinary Mos with tmux absent from PATH.

| Platform | Evidence/status |
|---|---|
| macOS 15.1, arm64, tmux 3.7c | Local installed-wheel qualification on 2026-10-03; xterm-256color PTY client, default tmux pane terminal |
| Linux | Qualification pending; run the same installed-wheel check on the supported host |
| Windows-hosted WSL2 | Qualification pending on an actual Windows host; Linux mocks do not qualify WSL2 |
| Native Windows | Outside this tmux slice; native availability remains subject to plan §27 |

The check covers workspace identity, Unicode drafts, paused queue and draft
preservation across real client detach/reattach, stable pane process identity,
exclusive controller rejection while detached, split/resize/zoom, transcript
navigation, queued-work cancellation and contextual recorded follow-ups, literal
single-line and multiline slash-command paste, normal Mos/client terminal-mode
and alternate-screen restoration, server loss followed by explicit saved-session
resume, and ordinary launch without tmux on PATH.

This evidence does not qualify live-provider interruption, every terminal emulator,
custom tmux configurations, Linux/WSL2, embedded terminals or the tmux control-mode
backend. Runtime Mos changes were not required for the locally exercised behavior.
Retain those separate platform and capability gates.

The local run used a fresh Mos 0.1.0 wheel built from runtime commit `aef2494`,
with Python 3.12.14 and prompt-toolkit 3.0.53. Its wheel SHA-256 was
`c12e8d4f1680d4319532fc6a3b082667aec7f3539ef111fd31c581093ed940f7`.
Twenty-two existing terminal tests and the new tool's lint/format checks passed.

Tmux command and binding reference: [official tmux manual](https://man.openbsd.org/tmux).
Use the manual for your installed version when bindings or command options differ.
