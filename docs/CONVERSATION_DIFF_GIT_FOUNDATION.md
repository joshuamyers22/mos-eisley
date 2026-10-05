# Conversation diff Git foundation

Status: implementation candidate; `make check` passes. This is the read boundary
required by
[plan §16.4.1](mos-eisley-plan.md#1641-v1--live-full-screen-diff-panel); it is not
the `/diff` panel or a prompt attachment implementation.

## Contract

`GitWorkspaceReader` takes an already admitted `DirectorySelection` and an
absolute trusted Git executable. It binds the selected directory, checkout root,
Git directory and executable identity. Its snapshot reports non-Git and unborn
HEAD explicitly. Changed paths are workspace relative; out-of-scope, non-UTF-8,
control-character and noncanonical paths are omitted with an incomplete-view
notice. A selected subdirectory cannot expose another subtree through a rename.

The inventory distinguishes staged, unstaged and untracked changes, preserving
rename source paths, deletions, binary counts and a digest of HEAD, staged object
identities, effective Git configuration, Git inventory output and workspace file
metadata. Patch reads require the exact current snapshot and one listed tracked
path. Untracked files are returned by path only. No untracked content preview is
available until the separate conversation workspace read policy exists. Patch
bytes are frozen with a digest. UI rendering must sanitize both path labels and
patch bytes; neither is an instruction or authority to send an attachment.
Submodule worktree dirt is ignored; a changed gitlink commit is shown in short
form. The broker never descends into a submodule's working tree.

The broker runs fixed Git commands without a shell under a minimal environment,
with system/global config suppressed, optional index locks disabled, Git hooks and
fsmonitor disabled, lazy fetch disabled, and external diff/textconv disabled. It
reads effective local
configuration under a 128 KB cap and overrides up to 64 configured clean, process,
smudge, external diff and textconv helper keys before every status/diff command.
The follow-on [process isolation hardening](CONVERSATION_DIFF_GIT_ISOLATION_WORK_NOTE.md)
wraps every command in an OS boundary: macOS Seatbelt denies network operations and
child processes while permitting only the trusted Git executable; Linux uses an
isolated installed-package launcher that applies `no_new_privs` and a seccomp filter
denying child creation, socket I/O and io_uring before replacing itself with Git.
The reader probes the boundary before classifying a directory as non-Git and
refuses when it cannot be enforced. These controls do not turn Git output into
trusted instructions or make the filesystem snapshot atomic.
This can make a filter-managed file appear modified against its normalized index
content; the panel must label the safe raw comparison rather than imply the
configured filter was applied. Local Git config remains data, so the explicit
switches and hostile-config tests are necessary. Each Git call has a 5-second
deadline. Inventories and staged object output each cap at 1 MB, lists at 512
files and patches at 256 KB.
Exceeding a cap fails the operation visibly; it never returns a truncated patch.

This API is synchronous. The future TUI must create a fresh reader for each
refresh, including after a non-Git directory gains a repository; call it off the
event loop, cancel obsolete refresh generations, and discard results after
directory switches.
The snapshot is a bounded stale-read detector, not an atomic filesystem
transaction: a malicious same-user process can race changes between checks.

## Work note and verification rubric

- Owner: Mos Eisley implementation; started 2026-10-02 UTC.
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`,
  `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, and `templates/WORK_NOTE.md`.
- Objective: provide the trusted read-only Git and workspace path foundation for
  the planned v1 `/diff` panel.
- Invariants: no provider calls, no Git mutation command, no external Git helper,
  no untracked content returned, no path escape, and no silent partial patch.
- Non-goals: panel layout, refresh scheduling, selected-line attachments, Git
  staging or editing, Windows qualification, and public release approval.
- Risk class: material new trust boundary. Accountable owner review is required
  before release or merge under repository `AGENTS.md`.
- Resource ceiling: the per-call bounds above; one full repository gate attempt
  plus targeted checks for concrete failures.
- Acceptance evidence: real Git repository tests for ordinary changes, non-Git
  and unborn HEAD, rename/delete/binary, subdirectory scope, hostile helpers,
  symlinks, stale snapshots, and resource limits; then `make check` once.
- Stopping rule: a failing boundary test or full gate blocks publication until
  corrected; no claim that this slice completes the full panel.

| Rubric dimension | Blocking threshold | Evidence |
|---|---|---|
| Selected-workspace isolation | No out-of-scope path or untracked-content read | Real subdirectory, rename and symlink-listing tests |
| Read-only Git execution | No helper execution or index write | Hostile-config and index tests |
| Bounded, truthful results | Cap failure visible; stale patch refused | Limit and stale-snapshot tests |
| Maintainable contract | Strict typing and full repository gate pass | Pyright, Ruff, `make check` |

## Threat model

| Abuse case | Control | Test / residual risk |
|---|---|---|
| Repository config runs a helper | Fixed Git argv and environment; disable fsmonitor, external diff, textconv, filters and hooks; require OS child-process and network denial for every Git call | Static helper and concurrent config-rewrite fixtures. Same-user mutation of trusted application/Git bytes remains outside this boundary. |
| Selected workspace is replaced | Bind device/inode for selected, root and Git dir; verify before and after reads | Directory replacement test. A same-user race between checks remains possible. |
| Git output names another workspace | Literal root-relative pathspec, path admission and scoped rename handling | Subdirectory crossing-rename test. |
| Untracked path is a symlink or special file | This foundation returns only its admitted path and never opens untracked content | Symlink listing test. Content preview remains blocked on a separate read policy. |
| Huge status or patch blocks UI | Child deadline and byte/file caps; future UI runs off event loop | Bound tests. Large inventories report failure until a bounded expansion design exists. |
| Partial clone fetches objects during a read | `GIT_NO_LAZY_FETCH=1` in the isolated Git environment | Missing local objects fail the read; no network fallback. |
| Source text injects terminal control or instructions | Reject unsafe labels; return patch bytes only as untrusted data | Renderer and attachment handling remain separate required work. |

## Evidence and handoff

The focused real-checkout suite is `tests/test_conversation_git.py`. Adversarial
checks found and closed stale same-count snapshots, a subdirectory pathspec rooted
at the wrong directory, rename patches displayed as additions, executable Git
clean filters, partial-clone lazy fetch, and untracked preview before a read policy.

- Focused Git suite: 13 tests passed. Ruff and strict Pyright passed.
- The earlier full-suite review failures were consistent with synthetic fixture timing:
  a probe retained a 30-second controller default and 10-second operation policy
  after its shared campaign fixture declared a longer duration. Its default
  phase signature lasted 20 seconds. The fixtures now use matching controller
  and operation budgets and longer test-only authority windows; explicit expiry
  tests retain their short certificates. Production limits were not changed.
- Elevated `make check` passed: Ruff formatting/lint and strict Pyright; 2,655
  source tests with four skips and 86% branch-inclusive coverage; export
  verification; wheel/sdist build; and 1,918 installed-wheel smoke tests. The
  elevated run was required for localhost socket-binding tests.
- Accountable owner security review remains required before merge or release
  under repository `AGENTS.md`.
