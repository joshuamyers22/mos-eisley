# PR 286: TLS fixture startup budget

- Status: fixture corrected; final combined validation and merge tracked in
  [PR 286](https://github.com/joshuamyers22/mos-eisley/pull/286).
- Owner: Joshua Myers; merge explicitly requested on 2026-10-05.
- Scope: integrate current main, correct the TLS test fixture, and merge after
  required checks pass. Live-session coding work in another worktree is excluded.

## Objective and invariants

Make the positive TLS startup test exercise the production read budget while
retaining authentication, owner admission, metadata-only persistence, revocation,
bounded request/handshake handling, and fail-closed cleanup. Production TLS and
read-lane limits remain unchanged. No provider, cloud, study, release, deployment,
or G4 milestone acceptance is part of this task.

The source job for revision `dc779dc` failed one TLS owner-admission test during
listener startup. The aggregate quality job consequently failed; installed-wheel,
container, Windows, POSIX storage, and secret checks passed. The shared source
fixture sets its read budget to 100 ms for hung-callback tests. TLS startup runs
real certificate validation in that lane, whereas the production default is two
seconds. A controlled 150 ms validation step reproduces the refusal with the old
fixture budget. The TLS fixture now selects a fresh default `ScheduleReads` lane
before attaching its owner. Explicit request/handshake deadlines remain selected
by their individual tests, and the short source fixture is unchanged.

## Selected guidance and verification

This material fixture investigation follows [Python engineering guidance](PYTHON_ENGINEERING_GUIDE.md),
the [verification guide](AGENTIC_VERIFICATION_GUIDE.md), and the
[verification loop template](../templates/AGENTIC_VERIFICATION_LOOP.md).
This note uses the [work-note template](../templates/WORK_NOTE.md). The
[threat-model template](../templates/THREAT_MODEL.md) directs review of the existing
authentication, replay, revocation, privacy, and denial-of-service boundaries.

Acceptance requires the delayed-validation regression, the TLS/loopback/read-lane
tests, the full combined `make check`, and all required GitHub checks. The focused
TLS suite has 18 passing tests, loopback has 16, and read-lane has four. Disposable
logs remain outside Git; final exact-revision results are recorded in the PR.
The local gate and one CI run are the initial validation budget; further runs
require an identified failure or a changed final revision. Stop on a clean gate
and verified merge, or report a concrete unmet protected-branch requirement.

Rollback is to revert the fixture change; this restores the short test budget
without changing production transport authority. Historical G4 milestone and
protected-service deployment limits remain separate from this engineering merge.
