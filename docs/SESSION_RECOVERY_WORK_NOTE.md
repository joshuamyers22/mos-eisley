# Session recovery verification

- Status: closed
- Owner: Joshua Myers
- Started (UTC): 2026-10-21
- Last updated (UTC): 2026-10-22
- Review or delete by: 2026-11-04
- Requirement: plan §31.4
- Baseline: 81134e0; clean branch `feat/session-recovery`

Objective: recover from verified owner-scoped session records without replaying a
possible write or paid call, losing steering, resetting reservations, or widening
execution authority. Keep the journal in the existing snapshot/SQLite session;
execution containers remain disposable. Legacy sessions remain readable.

Guidance: `PYTHON_ENGINEERING_GUIDE.md`, `AGENTIC_VERIFICATION_GUIDE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and
`templates/WORK_NOTE.md`. Material data-integrity and execution-boundary change.
Implementation and fault evidence do not constitute release/security approval.

Blocking rubric: ordered stable operation identities and immutable decision,
policy, target and reservation bindings before dispatch; atomic terminal evidence
and cursor; conservative uncertain recovery; bounded verified context and retained
steering/budgets; pinned replacement recipe and capability/workspace checks;
snapshot/SQLite and common TUI/plain/JSON projections. Test failures before dispatch,
after dispatch and before result publication, including lost acknowledgements.

Budget: three evidence-changing passes (focused fault matrix; source/static
regressions; full gate and installed-package verification), at most one combined
`make check`, zero paid provider calls. Stop when acceptance passes; on unresolved
boundary failure retain it as a blocker. Rollback: revert the coherent change.

Threats: duplicate paid/write dispatch after process/store/sandbox loss; stale
workspace or broader replacement mounts/capabilities; cross-owner replay; corrupt
or reordered records; premature result claims; hidden uncertain spending. Existing
private storage locks, hash verification, ledger holds, authorization, bounded
context selection and immutable no-mount containers remain authoritative. Same-UID
host/daemon compromise and external provider billing remain outside this change.

## Evidence and disposition

The 12 new recovery tests pass, including real-store commit/acknowledgement faults,
abrupt subprocess exit, retained steering, a real ledger's full unresolved hold,
scope refusal and shared UI projections. Focused child, live coding, live chat,
branch, working/cold storage, context, memory refresh and sandbox suites pass.
The new asynchronous container guard test verifies exact cleanup before start.

The first combined gate passed lint/format/strict typing, then exposed invalid
historical test fixtures: they changed completed session IDs or removed old
admission fields while retaining the new immutable journal bindings. That run was
stopped after failures were identified; it did not pass. Independent fixture
histories now create their own operation IDs, while explicit legacy fixtures omit
the later journal. Existing scope/admission diagnostics retain precedence, with
journal validation still mandatory afterward. All affected fixture suites pass.
The corrected runs followed those failures rather than adding an evidence-free
verification pass. No paid calls were made.

The final requirement trace found the recipe freeze also needed a durable child
reference. The second combined run was stopped before completion for that material
correction. Docker adapters now expose a deterministic recipe digest, retained in
the child record and journal decision and compared before execution/integration.
New tests cover a commit-time recipe change before any child call and changed
recipe rejection after both-store reload. The successful combined gate followed;
earlier interrupted runs are retained as unsuccessful attempts. This explicitly revises
the initial single-run ceiling in response to failures and the missing guarantee.

The later combined run identified UI fixtures that replaced a committed answer.
They now obtain long text through a controlled model client, preserving genuine
request/result bindings; focused activity/presentation checks pass. Diff-panel
timeouts were traced to `OS Git isolation is unavailable` in the execution sandbox,
not bypassed or converted to skips. That run was stopped. Approved native execution
subsequently exercised the required macOS isolation controls successfully.
No interrupted or sandbox-blocked gate is a pass.

The final native gate uses `make build` followed by `make check -o build -j4`:
the artifact is built first, then source/installed-wheel/static/export checks run
concurrently against frozen code. The intervening sequential native run was
stopped to use this equivalent dependency-safe schedule, not counted as passing.
Both commands completed with exit zero. Lint/format, strict typing and dependency
export checks passed. Source: 3,793 tests, 17 existing platform skips, 85% coverage.
Installed wheel: 2,760 tests, 13 existing platform skips, including recovery and
durable-recipe cases. Skipped native/platform checks are not qualification evidence.

## Close and promote

Stop reason: passed. All blocking rubric dimensions have passing source and
installed-package engineering evidence; no implementation finding remains open.
The immutable tested development wheel is identified in `SESSION_RECOVERY_VERIFICATION.md`.
The maintained contract, threat model, ADR-0017, project plan, roadmap and project
memory now describe the implemented boundary. Earlier failed/interrupted runs are
retained above and are not reported as passes. No paid provider calls or release
qualification were performed. Existing live/platform/release gates retain their
scope. New journal-bearing sessions require a compatible reader; rollback retains
that reader and pre-change backups. Disposable wheel/test directories were removed
by their owners; ignored build artifacts remain available for review.
