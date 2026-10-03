# Bounded-reader platform extraction

Status: local implementation verified, native CI pending. Started: 2026-10-03.
Owner: repository maintainer. Base: a1cb38b, initially clean
`refactor/platform-bounded-read` worktree. Review before merging.

## Objective and rubric

Extract the §27.2 bounded regular-file reader while retaining the public
`run.files.read_bounded` API. Blocking evidence: byte-exact bounded POSIX reads;
final-symlink and special-file refusal without FIFO blocking; descriptor cleanup;
invalid limits rejected before I/O; inert imports and explicit unsupported-platform
refusal; source and installed-wheel contract tests. Native Windows execution is
pending CI and does not qualify the whole CLI.

Invariants: opened-descriptor type checks, O_NOFOLLOW and O_NONBLOCK admission,
limit+1 read cap, overflow refusal, no fallback reader. Non-goals: native Windows
reading, ownership/ACL checks, ancestor containment, hardlink refusal, snapshots,
other platform contracts, process isolation or release approval.

Risk: material filesystem boundary. Budget: three correction passes and four hours
of active implementation; one frozen combined `make check` plus focused failure
reproduction if necessary. Stop when blocking evidence passes; report genuine
external-platform uncertainty. Do not weaken unrelated gates or publish failures.

## Context and selected guidance

[Python guide](PYTHON_ENGINEERING_GUIDE.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md),
[work-note template](../templates/WORK_NOTE.md),
[verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), and
[threat-model template](../templates/THREAT_MODEL.md) selected for this material
extraction. Existing reader, store tests, installed smoke runner and CI inspected.

## Boundary and abuse cases

Untrusted path/limit enters a caller-owned filesystem; returned bytes inherit the
caller's sensitivity. No new dependencies, credentials or writes. Final symlink
replacement is blocked by descriptor admission; FIFO denial of service by
nonblocking open followed by regular-type inspection; oversized inputs by a capped
read and refusal. Negative/noninteger/bool limits now fail before opening, an
intentional tightening. Unsupported systems must fail before importing the POSIX
adapter or opening a file. Concurrent content changes, ancestor symlinks, hardlinks
and ownership policy remain outside this primitive's guarantees. Native Windows
must obtain a separately reviewed adapter before being admitted.

## Evidence and handoff

| Pass | Evidence added | Result |
|---|---|---|
| Characterization | Four tests against the original reader before extraction | Passed; directory stream wrapping raises IsADirectoryError, retained in the contract |
| Extraction and faults | Ten isolated source/wheel tests, plus six existing store/CLI tests | Passed; symlink substitution, FIFO deadline, limit+1 read requests, cleanup and unsupported import/refusal covered |
| Frozen combined gate | `make check` | Exit 0: 2,652 source tests in 2,126.531 seconds (four existing skips), 86% coverage; 1,928 installed-wheel tests in 1,447.089 seconds, no skips; lint, strict typing, export verification and builds passed |
| Platform helper/configuration | Fresh wheel-only environment, native-host flag and CI dependency inspection | Ten tests passed; native-required flag correctly exited 2 on macOS; quality aggregate depends on Windows job |

The descriptor admission still belongs to the original opened object. Final-path
substitution with a symlink is refused; ancestor traversal and hardlinks remain
allowed. Stream-wrapping failure now closes the descriptor. Invalid limits are an
intentional tightening, not a claim of unchanged behavior for invalid inputs.

Checks ran locally on macOS. The Windows job has been configured but not run on a
native Windows host; Ubuntu CI for this branch is also pending publication.
Simulated Windows refusal does not replace that evidence. Full Windows reading,
other platform boundaries and CLI support remain open. Accountable review remains
required before native qualification or release.

Documentation links and `git diff --check` passed. Earlier plan/survey worktrees
retain their existing local edits. This batch is recorded on `refactor/platform-bounded-read`; no push, PR or release
was performed. Disposable
check output stays outside Git in `/private/tmp/mos-platform-files-check.log`.
The durable contract is recorded in [the guide](BOUNDED_FILE_READER_CONTRACT.md),
plan §27.2, ROADMAP and the evidence-linked platform memory entry.

Next smallest action: publish this committed batch for Ubuntu and native Windows
CI and review. No publication or release approval is implied by these local
results.
