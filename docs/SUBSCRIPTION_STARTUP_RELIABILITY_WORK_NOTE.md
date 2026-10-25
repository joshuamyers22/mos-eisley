# Subscription startup reliability investigation

- Status: bounded investigation complete; historical cause undetermined
- Owner: Joshua Myers
- Started: 2026-10-23 UTC
- Baseline: main `f31b4dd`; published rc.7 runtime `78bc17c`
- Branch: `fix/subscription-startup-exit`

## Objective and invariants

Investigate two earlier nonzero plain/piped ChatGPT empty starts whose child
statuses were lost by the qualification harness. Capture PID, timestamps,
return code/signal, timeout, stdout and stderr before evaluating success. Fix
only a reproducible defect, with behavioral regression coverage. Verify fresh
and resumed startup for both subscription providers without sending messages.
Preserve immutable rc.7, owner state, credentials, original grants and ledgers.
No additional inference, authorization recovery, publication or release changes.

Selected guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/WORK_NOTE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/INCIDENT_REVIEW.md`.
Context: README, project brief/memory, `docs/SUBSCRIPTION_SESSIONS.md`,
subscription launcher, plain terminal input reader, launcher tests, original
private rc.7 packaging checks and their retained diagnostic results.

## Bounded verification

Material investigation, ordinary local QA; zero model invocations. Initial
matrix: published native runtime, two providers, fresh/resume, pipe `/quit`/EOF
(eight phases), at most 90 seconds per phase. Fresh authorization is solely for
empty startup, never replacement authority for a failed inference. Stop on any
usage ledger entry or unexpected input. One additional targeted comparison per
new failure mechanism, at most two correction iterations. If no failure can be
reproduced, retain uncertainty rather than inventing a runtime fix. Preserve
diagnostics outside Git in ignored `.work/`. Focused regressions and static
checks follow any correction; run the combined `make check` once before any
publication. Publication is outside this task.

Acceptance: every attempted child status retained, no inference dispatch,
unchanged original grant across resume, saved sessions on clean termination,
actionable classification for failures. Historical lost exit codes cannot be
recovered; clean later runs alone cannot establish their cause.

## Observations

The original `check_tagged_packaging.py` saved stdout/stderr but asserted on
return code before persisting it. Later captured pipe fresh/resume checks and
normal-terminal checks passed. Claude account access under sandbox restrictions
was separately refused and passed on the normal host. Earlier ChatGPT cause
remains undetermined.

## Handoff

The published rc.7 Mac arm64 executable passed all eight normal-host phases:
both providers, fresh/resume, piped `/quit`/immediate EOF. Every child exited 0,
saved its session, displayed the correct provider, retained the original grant
despite a higher requested limit on resume, and left its usage ledger empty.
Executable SHA-256:
`779d3461af86ff002165dadc174d9df5519c25d9695640e77b9783603e1ced91`.
Private results: `.work/native-matrix/results.json`, with individual status,
stdout and stderr files. All ten native phases across this investigation sent
zero model messages; native metadata checks are not inference.

One additional controlled comparison checked the original restricted pipe
context: ChatGPT fresh/resume with `/quit`, using the same standard-utility PATH
as the old harness. Both exited 0 with saved sessions, identical authorization
bytes and empty ledgers. Results: `.work/restricted-comparison/`. This environment
comparison adds evidence about the historical context, rather than repeating the
normal-host matrix. Claude's earlier sandbox account refusal was already
classified separately; it was not retried here.

No application failure was reproduced and no runtime change is justified by
these results. The two historical child statuses were never persisted and cannot
be recovered. Their cause remains undetermined; this is not a root-cause fix or
a general subscription-reliability qualification. Stop at the bounded evidence
threshold rather than repeat successful starts until claiming resolution.

## Diagnostic correction and regression coverage

`tools/capture_startup.py` fixes the observable qualification-harness defect:
persist actual PID, start/end timestamps, return code/signal and timeout state
before output decoding or success assertions. Capture raw stdout/stderr in a
new private directory, refuse to overwrite evidence, kill/reap the process group
on deadline and never retry. Input is fixed to `/quit` or EOF. The helper exits
unsuccessfully on a nonzero, signal, timeout or failed spawn; saved-session output
alone does not imply success. It is a diagnostic utility, not launch authority.

`tests/test_startup_capture.py` uses real child processes to cover application
exit 7 with non-UTF-8 output, SIGTERM, forced timeout with partial output and
child reaping, failed spawn and evidence-overwrite refusal.
`tests/test_subscription_startup_process.py` covers eight cold process phases
through the real CLI/launcher/storage stack with metadata-only native fixtures.
It checks clean child exit, saved labels, retained one-call authorization despite
requesting two on resume, empty usage ledgers and the exact native metadata call
list. Any inference command is refused and fails the call-list assertion.

For future native qualification, use the helper with the owner-approved command
and a new private output directory, then check the saved state and ledger:

```sh
uv run --frozen python tools/capture_startup.py --help
# --output NEW_PRIVATE_DIRECTORY --cwd EMPTY_WORKSPACE --ending quit|eof
# -- mos subscription chat [explicit approved route, state and consent options]
```

Do not paste credentials, account output or private captures into Git. A future
recurrence must retain its actual process outcome and execution context before
any attempt at diagnosis; do not automatically retry or replace its grant.

Validation passed: 11 subscription-launcher tests, 12 startup tests (including
the four capture failure tests and the eight-phase cold-process matrix),
repository-wide lint/format (1,405 Python files), and canonical frozen Pyright
(zero errors/warnings). Full `make check`, installed-wheel and cross-platform
qualification were not rerun: no runtime or dependency changed and no publication
is being attempted. They remain required before publishing this branch.

The published binary, owner shortcuts, credentials and existing sessions remain
unchanged. No release or publication is part of this task.

## Merge preparation

The owner subsequently requested commit/push and preparation for merging. Initial
investigation commit: `eff25a5`. Main remains `f31b4dd`; the branch has no missing
main commits or existing PR. Scope: inspect the complete diff, run one combined
`make check` including installed-wheel smoke, create a PR with precise limits,
and inspect required checks/review readiness. Zero provider inference remains
mandatory; do not replay native qualification or change release artifacts.
Keep raw gate logs private in `.work/merge-check.log`. Bound remediation to two
evidence-backed corrections; investigate actual failures rather than retrying
unchanged checks. The seven protected checks (quality, container, gitleaks and
four native targets) and resolved review conversations are required for merge.

Review found that the clean-wheel smoke runner explicitly selects tests and
helpers: the two new startup test modules were absent from its list. Add both
modules and the capture helper so the same cold-process matrix also exercises
the installed wheel without the source package. No application/runtime change.
That startup-branch local gate passed 3,810 source tests but its installed-wheel
run failed four review-fixture setups with `verified critic quorum was not met`.
It is not counted as passing. Its GitHub checks passed independently. The
[rc.8 integration](RC8_REVIEW_PREVIEW_WORK_NOTE.md) includes these commits and
tracks the fresh combined gate and final CI. Its focused 134-case batch includes
all four prior failures and passed; this does not establish their historical cause.
