# ADR-0015: Confine `/diff` Git reads at the OS process boundary

- Status: proposed; accountable owner security review pending
- Date and owner: 2026-10-03, Josh Myers
- Requirement: [owner `/diff` review](../CONVERSATION_DIFF_OWNER_SECURITY_REVIEW.md)

## Context and options

The `/diff` reader loads Git metadata from an owner-selected workspace. Local
configuration and attributes can name helper commands, and a concurrent rewrite
can occur after the reader scans helper keys. Fixed Git arguments, a minimal
environment, and configuration overrides reduce that risk but cannot make the
scan and Git launch atomic. Keeping those controls alone leaves a helper-launch
race. Rejecting all local Git configuration would impair ordinary repository
reads and still leave the process boundary implicit.

## Decision and consequences

Run every `/diff` Git command inside an OS-enforced boundary. On macOS, Seatbelt
denies networking and child creation while allowing execution of the bound trusted
Git binary. On Linux x86_64 and aarch64, an installed-package launcher enters
Python isolated mode, sets `no_new_privs`, installs an inherited seccomp filter
that denies child creation and network syscalls, then replaces itself with Git.
Probe that boundary before even classifying a directory as non-Git; refuse reads
on unsupported or unavailable hosts. Retain the existing path, executable,
resource, helper-override, and stale-snapshot checks.

This adds a process launch to each Git command and limits `/diff` availability to
qualified hosts. Linux must permit the launcher's initial `execve`; the filter
persists into Git, while child creation and `execveat` are denied. A trusted Git
binary, installed application code, and the OS remain trusted. File writes are
not separately denied by this process policy, and a read is not an atomic
filesystem transaction. Removing the wrapper would reopen the race, so rollback
should disable `/diff` reads rather than use unsandboxed Git.

## Verification

Real host tests must show that a confined process cannot spawn a child or open a
loopback socket. A concurrent repository configuration rewrite must leave a
marker helper unexecuted; replaying the raced Git arguments without confinement
must execute it. Existing `/diff` snapshot, patch, packaging, and full project
gates must pass. The [work note](../CONVERSATION_DIFF_GIT_ISOLATION_WORK_NOTE.md)
records host evidence; the [threat model](../CONVERSATION_DIFF_GIT_ISOLATION_THREAT_MODEL.md)
records residual limits. Reconsider if a target host cannot enforce the boundary
or legitimate Git reads require child processes that the policy must deny.
