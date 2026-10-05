# Work note: connected live session coding

- Status: source implementation and requested bounded functional live qualification
  complete; final delivery CI and accountable release disposition are recorded in
  [PR #287](https://github.com/joshuamyers22/mos-eisley/pull/287).
- Owner: Codex implementation; Joshua Myers owns operating scope and release review.
- Started: 2026-10-05
- Starting revision: `374dae8`, clean isolated `feat/live-session-coding` worktree.
- Selected guidance: `PYTHON_ENGINEERING_GUIDE.md`,
  `AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
  `templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`,
  `ADVERSARIAL_REVIEW_PLAYBOOK.md`,
  `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md` and plan §7.7.1.
- GitHub template guidance checked at
  [`71ad8786d02bc8e5656ec10b43896c5c36336656`](https://github.com/joshuamyers22/production-project-template/tree/71ad8786d02bc8e5656ec10b43896c5c36336656):
  `AGENTS.md`, Python engineering and bounded verification guides. The applicable
  current guidance agrees with Mos Eisley's pinned copies. Selected rules are
  immutable contracts, narrow injected collaborators, early failure tests, owned
  cancellation, frozen dependencies, artifact verification and separate accountable
  approval for release/security decisions.

## Objective and rubric

Connect explicit `/implement` to creator planning and executable test derivation,
blind critic/judge review, exact creator approval, a fresh coding child, bounded
correction, isolated tests, guarded Git integration and post-integration tests.
Use the existing OpenAI/Anthropic provider, spending, Docker and VCS boundaries.
Recorded workflows must remain compatible. This implementation does not qualify
a release, broaden the pure-Python execution profile, run a study or enable routing.

Blocking checks: all required phases precede integration; tests cannot be weakened;
source changes invalidate approval; rejected review cannot integrate; cumulative
call/cost/byte/wall limits cover every role and correction; cancellation and crash
never replay a call or integration; snapshot and SQLite resume preserve identity.

Risk: high, because paid calls and repository integration cross trust boundaries.
Verification budget: focused behavior/failure tests, static checks, one combined
`make check`, then affected checks for fixes. No paid requests during implementation.
Accountable release and live-candidate qualification remain separate from source tests.

## Assets and threats

Source/tests and provider responses remain in owner-only local artifacts. Credentials
stay in the host transport, never worker stdin or stored selection/session state.
Every role gets an explicit task packet; critics and judge do not receive chat history.
Untrusted source, plans and responses cannot change the selected scope or install tools.
Creator tests are additional private artifacts, frozen before child dispatch, and
never overwrite existing repository tests. Git writes remain source-only.
Duplicate attempt directories reject before provider work. Before-send records and
existing conservative spending receipts preserve uncertainty. Changed source, owner,
policy, role identity or expiry stops new work. No automatic retries or refunds.

## Completion evidence

- Focused live workflow: 18 tests passed from source and against the rebuilt wheel,
  including both provider spending adapters with fixture transports, cancellation,
  immutable tests, bounded correction, exact review/approval and both session stores.
  The final added check rejects unsupported source before the first paid planning
  call. This bounded correction followed the combined gate's initial source batch;
  affected source/wheel checks were rerun.
- Existing coding controller/VCS/worker checks: 51 tests passed.
- Real unpaid Docker/Git smoke passed for successful integration, failed-test
  correction and rejected final review. Worker image:
  `sha256:11023d7c1443bdb03365e3eb93bd29f59c6da5b5e3333f762e0db33a89ea9763`.
  Provider responses were fixtures; this is containment/integration evidence.
- Ruff and Pyright passed. Frozen dependency-export verification, source archive
  and wheel builds passed. The new suite is included in future wheel smoke checks.
- Full installed-wheel smoke passed: 2,559 tests, 13 platform skips. Its initial
  batch wheel preceded the final admission correction; the rebuilt wheel's 18
  affected workflow tests passed separately.
- Combined `make check` ran 3,571 source tests: 5 failures, 84 errors and 17 skips.
  Local socket bindings, tmux sockets and nested macOS Git isolation were denied
  by the execution sandbox; two memory-mapping subprocesses also timed out while
  source and wheel suites ran concurrently. All 145 tests in the affected suites
  passed when rerun outside the sandbox, including those mapping cases. Two diff
  timeouts also reproduced on unchanged starting main inside the sandbox; the
  outside-sandbox run resolved them without source changes.
  The initial batch's coverage report passed the repository's 84% threshold.
  Because `make check` stopped at its source-test target, dependency export,
  builds and the full installed-wheel smoke were completed separately. The
  original sandboxed command itself is not reported as passing.
  The exact starting main revision passed
  [GitHub Linux CI](https://github.com/joshuamyers22/mos-eisley/actions/runs/37331224069);
  this is baseline context, not candidate-branch CI qualification.
- No paid provider requests occurred during the original source implementation
  phase. Subsequent live qualification and its retained charges are recorded below;
  no merge or release was performed.

## Remaining release evidence

The [budgeted live qualification work note](LIVE_SESSION_CODING_QUALIFICATION_WORK_NOTE.md)
records all four requested functional scenarios passing on committed runtime
candidate `44adf47` with the existing qualified Sol/medium, Luna/low, Terra/low,
Sonnet 5/low and Opus 5.5/low routes. Live-discovered contract corrections include
feasible plan approval, consistent budget interpretation and ordered chunking of
large role packets. All 19 affected source and installed-wheel tests passed after
these changes. Accountable final cancellation reconciliation preserved its original
receipt and settled the charge at $0.022624. Total settled spending is $2.375657
under the unchanged $10 cap, with zero unresolved entries; see the
[release work note](LIVE_SESSION_CODING_RELEASE_WORK_NOTE.md).

The completed demonstration binds the exact
candidate, selected roster, reviewed policies, shared ledger, synthetic operating
scope and immutable worker image.
Accountable review must assess the new paid-call/integration composition beyond
this implementation assessment. General repository coding, goals and forks remain
outside this candidate's supported operating profile.
