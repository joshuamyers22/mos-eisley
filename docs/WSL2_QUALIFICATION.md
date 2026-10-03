# WSL2 setup and qualification preparation

WSL2 is a **planned** Windows-host deployment under
[plan §27.1](mos-eisley-plan.md#271-version-010--supported-wsl2-deployment).
This runbook prepares a real Windows-hosted runner; passing the diagnostic below
does not qualify platform support, a sandbox, live providers or a release.
Native Windows and WSL1 are outside this deployment contract.

## Set up the Windows host

Use a Windows host meeting Microsoft's current
[WSL installation prerequisites](https://learn.microsoft.com/en-us/windows/wsl/install).
In an administrator PowerShell window, install a distribution, restart if prompted,
and complete creation of a non-root Linux user:

```powershell
wsl --install -d Ubuntu-24.04
```

In PowerShell, retain Windows version/build from Settings → System → About and
the outputs of these [WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands):

```powershell
wsl --version
wsl --status
wsl --list --verbose
```

The selected distribution must show version **2** in `--list --verbose`.
If a legacy installation does not implement `--version`, update WSL before using
this qualification recipe. Do not infer version 2 from a distribution's name.
Use Windows Terminal's distribution profile, or enter its home directory from
PowerShell with `wsl -d Ubuntu-24.04 --cd ~`. Verify `id -u` is nonzero inside Linux.

Keep repositories, worktrees, installed environments, configuration, memory,
credentials, evidence and session storage inside the distribution's Linux
filesystem. Microsoft's [filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems)
also recommends keeping Linux-command projects there. `/mnt/c`, DrvFS, network
shares, host Docker/editor sockets and their aliases need separate qualification.
This recipe initially admits only ext4 as a filesystem candidate.

## Install an exact candidate inside Linux

Install Git, make and optional tmux using the distribution package manager. Install
Linux uv using its [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/),
then install Python 3.12 with `uv python install 3.12`. Use Linux executables;
Windows Python/uv/Git on the inherited PATH are not this installation.

Clone the repository under `~/Projects`, check out the **full reviewed candidate
commit**, and record it. Replace `FULL_REVIEWED_COMMIT` before running:

```sh
mkdir -p ~/Projects
git clone https://github.com/joshuamyers22/mos-eisley.git ~/Projects/mos-eisley
cd ~/Projects/mos-eisley
git checkout --detach FULL_REVIEWED_COMMIT
git rev-parse HEAD
git status --porcelain
uv sync --frozen --dev
make build
```

Do not proceed with a dirty candidate or undocumented patches. Build outputs
are local candidates, not proof of publisher authenticity. Use the reviewed
release artifact and its verification policy when qualifying a release.

Install the built wheel into a separate Linux environment with hash-pinned runtime
dependencies. These paths belong to this recipe, not the application's defaults:

```sh
umask 077
mkdir -p ~/.local/share/mos-eisley-qualification/sessions
mkdir -p ~/.local/share/mos-eisley-qualification/evidence
uv venv ~/.local/share/mos-eisley-qualification/venv --python 3.12
uv pip install --python ~/.local/share/mos-eisley-qualification/venv/bin/python \
  --require-hashes -r requirements.runtime.txt
uv pip install --python ~/.local/share/mos-eisley-qualification/venv/bin/python \
  --no-deps dist/mos_eisley-0.1.0-py3-none-any.whl
sha256sum dist/mos_eisley-0.1.0-py3-none-any.whl requirements.runtime.txt uv.lock
```

`mkdir` does not fix permissions on existing directories; inspect existing paths
before reuse. Keep outputs private. For a later package version, use the matching
wheel filename. Resolve any inherited `PYTHONPATH` override before verifying the
installed package; the following commands clear it explicitly.

## Run read-only preparation preflight

From **outside the checkout**, use the installed interpreter:

```sh
cd ~
env -u PYTHONPATH ~/.local/share/mos-eisley-qualification/venv/bin/python \
  -m mos_eisley.wsl2_preflight \
  --workspace ~/Projects/mos-eisley \
  --storage ~/.local/share/mos-eisley-qualification/sessions \
  --private-dir ~/.local/share/mos-eisley-qualification/evidence \
  > ~/.local/share/mos-eisley-qualification/evidence/preflight.json
```

Exit 0 means the preparation checks passed; exit 2 means rejection. JSON always
sets `platform_qualified` and `execution_authorized` to false. It records installed
package/Python versions, distro, architecture, kernel, resolved selected paths,
covering mount filesystem, and stable issue codes. Add `--private-dir` for each
existing memory/config/credential directory you intend to use, up to 16. It reads
directory metadata only, never private files or an environment dump.

The preflight requires a recognized Microsoft WSL2 kernel marker and a non-root
POSIX user. WSL1, ordinary Linux/macOS, custom or ambiguous kernels, missing distro
or mount metadata, unqualified or read-only filesystems, and public/foreign private
directories reject. The [mountinfo parser](https://man7.org/linux/man-pages/man5/proc_pid_mountinfo.5.html)
uses the longest component-matching mount after resolving directory aliases;
stacked ambiguous mountpoints reject. Kernel strings are not authenticated host
provenance. Custom kernels require separate review rather than a bypass switch.

This is a point-in-time diagnostic. It does not validate directory contents,
ancestor ACLs, secure replacement/locking/durability, keyring access, containment,
Windows-host identity or a selected execution backend. Existing runtime checks
remain authoritative. The report says `execution_backend: not_probed`; record the
actual backend and its immutable image identity separately during containment tests.

## Verify source and installed artifact on the real runner

Record command, candidate revision, wheel SHA-256, environment, return code,
test/pass/skip counts and bounded failure summaries for each gate. Do not retain
raw credentials, provider payloads, conversation content or unrestricted logs in
the qualification record. Do not claim skipped tests passed.

| Gate | Procedure | Required evidence |
|---|---|---|
| Environment | Host commands and installed preflight above | Actual Windows version/build, WSL component version, selected distro version 2, kernel, architecture, ext4 paths and non-root UID; operator/date |
| Combined quality | `make check` in the frozen checkout | Source tests, typing/lint, coverage, dependency export, build and installed-wheel smoke all pass; actual counts/skips recorded |
| Installed ownership/storage/conversation | `make smoke` (already part of `make check`) | Clean temporary wheel install outside source; conversation, save/resume, memory, SQLite, cancellation and synthetic OAuth suites; no real provider credentials |
| Human terminal behavior | Launch installed `mos` command below in Windows Terminal | Unicode/multiline paste, draft, resize, scroll, cancellation, save/quit and exact-ID resume, with queued work still paused |
| Optional external tmux | After the separate tmux PR is in the chosen revision, install tmux and run `MOS_REQUIRE_TMUX=1 make check` | Actual `tmux -V`; source and installed-wheel compatibility tests pass; absence of the tests is **pending**, not a pass |
| Linux containment | Review Docker/image provenance, then run `make container` in the frozen checkout | Real positive/negative offline containment, resource limits, cancellation and descendant cleanup; active Linux-local daemon/backend and immutable image recorded |
| Git/worktrees | Check the reviewed candidate's implemented Git suites and exact installed behavior | Linux Git/path/worktree ownership, locking and cleanup evidence; planned capabilities remain pending when absent |
| Credential store | Review selected Linux keyring backend on the runner | Synthetic OAuth package tests do not qualify the real Linux secret service; separately qualify storage permissions, login/refresh/logout and denial behavior before claiming credential support |

`make check` takes substantial time and `make smoke` builds its own temporary
installed environment. Do not rerun smoke separately when the combined gate
already passed for the same wheel. Dependency installation needs network; fixture
tests use synthetic data and may use local loopback sockets. Container work needs
a reviewed **Linux-local** Docker daemon and may build images; Windows-host socket
bridges are outside this recipe. If unavailable, mark containment pending and keep
security-sensitive execution disabled. No live provider, study or production
sampling command is part of this procedure.

For the human terminal check, start from `~/Projects/mos-eisley`:

```sh
env -u PYTHONPATH ~/.local/share/mos-eisley-qualification/venv/bin/mos \
  chat --no-memory --storage ~/.local/share/mos-eisley-qualification/sessions
```

Use the built-in recorded preview and its advertised prompts. Save with `/quit`,
record the session ID, and resume that exact ID with the same workspace/storage.
Do not use `--last` to assert exact-session identity. See the
[terminal guide](CONVERSATION_TUI.md). After the separate tmux PR lands, its guide
and tests supply the external-workspace procedure; this branch does not copy them.

## Upgrade, diagnostics and uninstall

Before an upgrade, save and stop sessions, retain private backups with their owner
and mode, and freeze the old version/wheel identity. Build and verify the reviewed
new revision, install it into a **new** Linux virtual environment with its matching
hash-pinned runtime requirements, then repeat qualification. Test resume with
copies of saved sessions before switching launch paths. Keep the old environment
for rollback; do not downgrade migrated data without a verified reverse path.
Guided automatic update/restart under §28 remains planned.

If preflight rejects, inspect only its issue codes and the selected directory
metadata (`stat`, `findmnt -T PATH`), `uname -r`, `/etc/os-release`, Linux executable
locations, and host `wsl --list --verbose`. Move unqualified paths into the Linux
filesystem, select a non-root user, or correct private-directory ownership/mode
deliberately. Never fix rejection by relabeling ordinary Linux as WSL2 or weakening
runtime checks. Do not dump environment variables or credential contents.

Uninstall only the dedicated virtual environment after stopping its processes and
backing up any required state. Remove a launcher only if it points to that exact
environment. Session/memory/credential data requires separate explicit deletion;
uninstalling the CLI does not authorize it. Do not use `wsl --unregister` as a Mos
uninstaller: it deletes the entire distribution.

## Qualification record and acceptance

Create a private record with the following fields; leave unknowns pending:

```text
Status: pending / failed / qualified-for-exact-reviewed-scope
Owner/reviewer and UTC date:
Windows edition/version/build and host-side WSL evidence:
Distribution/version, kernel, architecture and non-root UID:
Candidate full commit; clean-tree check; wheel SHA-256:
Runtime requirements/lock hashes; Python/uv/Git/tmux versions:
Selected filesystem/mounts; private preflight result:
Actual execution backend/daemon location/immutable image and boundary evidence:
Source and installed-wheel results, counts, skips and durations:
Terminal, Git/worktree and real credential-store results:
Unsupported or untested boundaries; failures; recovery/rollback evidence:
Accountable approval and exact advertised feature/platform scope:
```

Accountable review must verify the Windows host and exact installed artifact and
close every applicable §27.1 gate before claiming WSL2 support. Fixture results,
Ubuntu CI and this preparation command do not supply that evidence. The current
preparation status is **ready for runner execution; actual WSL2 qualification pending**.
