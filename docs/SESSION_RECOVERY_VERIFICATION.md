# Session recovery verification

- Requirement: plan §31.4; baseline 81134e0; branch `feat/session-recovery`
- Owner: Joshua Myers
- Scope: session operation journal, shared dispatch guard and pinned container recipe
- Guidance: Python engineering, bounded verification loop, work note, threat model
  and adversarial review templates selected under repository `AGENTS.md`
- Verification perspective: same implementing agent; no independence claim
- Full-gate result: passed, 2026-10-22 UTC; see `SESSION_RECOVERY_WORK_NOTE.md`

Installed artifact: development wheel `mos_eisley-0.1.0rc5-py3-none-any.whl`,
SHA-256 `b7f42414bdad752e83d6c4952bdb5532ad2eec4650277a0d1847d3d051914472`.
The isolated wheel suite passed 2,760 tests with 13 existing platform skips after
installing 42 hash-locked runtime dependencies. This is the development artifact
for the frozen implementation, not a publication or release qualification.
The final gate runs `make build` first, then `make check -o build -j4` so the
verified artifact is immutable while source and installed tests run concurrently.

## Blocking rubric and acceptance evidence

| Dimension | Threshold | Evidence |
|---|---|---|
| Recovery correctness | No duplicate write/paid dispatch; known committed result retained | Real snapshot/SQLite dispatch/result transaction and acknowledgement matrix |
| Retained user intent | Outstanding steering/ancestry and bounded context survive restart | Abrupt subprocess termination, cold/working state, continuation/context regressions |
| Resource integrity | Consumed attempt and full unresolved paid hold survive | Synthetic live runner with real persistent ledger; child/goal/live coding regressions |
| Scope | Foreign owner/workspace refuses; changed source/tools cannot dispatch | Real-store negatives, per-call dispatch guard and target-replacement test |
| Sandbox replacement | Immutable no-mount recipe; denial after create cleans exact ID without start | Recipe-drift tests and controlled Docker/real worker-pipe broker regressions |
| Interface and package | Same uncertainty through TUI/plain/JSON and installed wheel | Shared-controller projections, `mos exec`, isolated wheel acceptance suite |

## Evidence-changing passes

1. Focused real-store fault matrix, real process exit, real ledger exposure and
   UI projections. Twelve new recovery tests pass; subcases cover both backends.
2. Broader child, coding, live-chat, branch, storage, context and sandbox regressions;
   global lint/format and strict typing. The final combined gate passed, including source
   coverage and clean installed-package tests.
3. Review final requirements against those executable boundaries, retain failed
   attempts and corrections, and promote only supported facts to maintained docs.

Initial budget: three evidence passes, zero paid calls, one combined full gate.
The single-run ceiling was revised after actual failures and native OS admission
requirements, as recorded below and in the work note. Stop on
passing gates or a reported unresolved blocker; additional unrelated repetition is
not verification. Release/security approval requires accountable review beyond this
agent-authored record.

## Findings and corrections

| Finding | Consequence | Correction and verification |
|---|---|---|
| Ordinary manual state reconstruction omitted local child records | A later conversation transition could lose child recovery/resource history | Preserve children in ordinary and memory-refresh transitions; queue-retention regression |
| Hashing an entire completed entry included a materializable legacy memory reference | Memory refresh could falsely invalidate an unchanged committed answer | Hash immutable admitted request/outcome fields; refresh and cold-store regressions |
| Initial crash fixture assumed a normal completed-answer history | Interrupted-context request legitimately differed from the normal recording | Supply a dedicated controlled answer for new queued work; verify original operation is never called again |
| Initial terminal fixture used unsupported `/exit` | Test waited for more input | Use documented `/quit`; no product behavior changed |
| Older tests cloned completed IDs or removed admissions while retaining new journal bindings | Synthetic legacy/retention fixtures became internally inconsistent | Create independent recorded histories or explicitly complete the legacy downgrade; retain scope/admission diagnostic precedence and mandatory journal validation |
| Recipe freeze originally existed only in the active container object | A later adapter needed an explicit retained recipe reference | Persist recipe digest in child records and journal policy; compare before execution and coding integration; both-store and commit-race tests |
| UI fixtures edited a committed answer to create scrolling content | The new result integrity check correctly rejected later transitions | Produce the long answer through a controlled model client; activity/presentation regressions |
| macOS Git isolation unavailable inside the execution sandbox | Diff-panel acceptance tests could not acquire their required OS boundary | Preserve controls and rerun the full gate with approved native execution; do not treat timeouts as skips |

The final contract does not replay intermediate tool calls, infer missing legacy
reservation evidence or advertise new native/live qualification. Same-UID host and
Docker daemon remain trusted. The rollback procedure retains compatible session
readers and backups because old binaries reject the new nested journal field.

The initial combined gate was stopped after those fixture failures. Its successful
static checks are retained, but the run is not a pass. A corrected combined gate
was stopped before completion when the requirement trace identified the missing
durable recipe reference. The successful combined gate followed the focused recipe tests;
neither earlier interrupted run is reported as a pass.
The subsequent sandboxed attempt also exposed the UI fixtures and unavailable OS
Git isolation. It was stopped; the corrected native gate then passed. An intervening
sequential native run was stopped to use the dependency-safe parallel schedule.
None of those interrupted attempts is counted as passing.


## Final gate

`make build` and native `make check -o build -j4` each exited zero. Building first
kept the wheel fixed while source, installed-package, static and export checks
ran concurrently. All lint/format and strict typing checks passed, dependency
export matched, and both wheel/sdist builds succeeded. The source suite passed
3,793 tests (17 existing skips) with 85% branch-inclusive coverage. The installed
wheel passed 2,760 tests (13 existing skips). Source ran for 3,002 seconds and
installed tests for 2,114 seconds, concurrently. These are actual completed gates;
skips are not native qualification. No paid provider calls were made.

Stop reason: passed. All rubric dimensions pass; no blocking implementation
finding remains. Accountable live/security/release acceptance retains its existing
separate scope. The contract, ADR-0017, plan, roadmap and project memory contain
the durable conclusions; the work note records initial failures and corrections.
