# Frozen watchdog dispatch repair

- Status: repair implemented and native-verified; combined quality gate passed.
  Owner: Joshua Myers; operator: Codex. Started: 2026-10-27.
- Branch: `fix/frozen-watchdog-dispatch`; baseline immutable rc.9
  `f94842a44b9fc5dcf42a7f5880a6683e4fdc0b23`; new candidate `0.1.0-rc.10`.
- Requirement: fix RC9-SUB-01 found by installed subscription qualification.
  The failed run and its three completed native invocations remain preserved in
  the separate rc.9 qualification worktree. No replay or new inference is part
  of this repair; no published artifact or rc.9 tag may change.

Signed rc.10 follow-through: [final qualification review](RC10_QUALIFICATION_REVIEW.md).
All four signed guardian/installed checks passed; the fresh live campaign advanced
past baseline cleanup but stopped at an Anthropic authentication diagnostic.
Full live acceptance remains incomplete; immutable rc.10 is published.

## Objective and acceptance

The standalone application must start its compiled-in detached container guardian
without treating itself as a Python interpreter. Preserve finite lease deadlines,
EOF-triggered exact-container cleanup, private receipts, descriptor custody,
readiness refusal, stripped credential environment, and ordinary CLI behavior.
Retain rc.9 dependency versions and epoch 2. Only project version changes to rc.10.

Guidance selected: repository AGENTS/CONTRIBUTING, Python Engineering Guide,
Agentic Verification Guide, adversarial review playbook and architecture-review
template, plus work-note, threat-model and verification-loop templates. Existing
README, brief, memory and rc.9 launcher work note establish the frozen scope.

| Blocking dimension | Acceptance evidence |
|---|---|
| Fixed dispatch | Frozen POSIX entry selects only the compiled-in watchdog; wrong platform/non-frozen mode refuses; arguments retain exact meaning |
| Lifecycle integrity | Native helper readiness, finite deadline and EOF cleanup produce bound private receipts; invalid lease fails closed |
| Real worker | Exact previously qualified image executes the retained synthetic brief with the actual new native guardian, without provider calls |
| Regression prevention | Standard standalone smoke executes native guardian on macOS/Linux, without host Python/Node dependency |
| Combined correctness | Focused lifecycle/dispatch tests, static checks and one combined `make check` before publishing a PR |

## Threat and stopping rules

The helper switch is an internal process entry, not caller-selected Python/module
execution. Dispatch before CLI/provider imports, only in the frozen POSIX app.
Existing explicit Docker path, exact container ID, lease bounds and inherited
read-descriptor contract remain authoritative. Direct local invocation grants no
provider, model, repository or release authority. Credentials stay excluded from
the guardian environment. No external Python fallback, new Docker mount/network
grant or changed lease duration. Agent assessment is not independent security or
accountable release approval.

Bound one coherent implementation, focused checks, one native build and real
guardian/worker evidence, then one combined full gate; four hours per full/native
gate, at most two evidence-backed corrections per new failure, zero inference.
Stop dependent work on failed assertions or identity/cleanup mismatch. Other
`sys.executable` sites receive a source audit, not automatic unrelated rewrites.
Protected signing, four-target release qualification and publication remain later
release operations; this task makes the repair reviewable and verifies its path.

## Verification and handoff

- Fresh isolated worktree created from exact rc.9; frozen dependencies installed
  from the local uv cache with no network or dependency updates.
- Implemented fixed `--_mos-container-watchdog` dispatch in the frozen POSIX
  entry before CLI/provider imports. The existing watchdog main accepts explicit
  argv. Frozen launch uses the fixed mode; source/wheel launch retains `-m`.
  No lease, FD, environment, Docker or removal policy was relaxed.
- Six frozen-entry and eight watchdog tests passed, including mode/platform
  refusal, exact argument routing, detached descriptor custody and excluded
  credentials. Seven isolation, 42 distribution and three workflow tests passed.
  Initial searches used two nonexistent test patterns and ran zero tests; those
  commands are not counted as passing. The actual isolation/distribution/workflow
  files were then selected and executed.
- Ruff/format and full strict Pyright passed. First combined `make check` ran
  3,882 source tests in 2,913.518 seconds, with 17 skips and two errors; it did
  not reach coverage reporting, export/build or clean-wheel smoke. The original
  `.work/watchdog-verification/make-check.log` is retained as a failed gate.
- `test_dispatch_timeout_skips_retained_intent_without_call_or_refund` expired
  its 100 ms read allowance during admission, before the intended slow-dispatch
  exercise. The fixture now applies that same allowance after valid admission;
  production code, deadline and no-call/no-refund assertions are unchanged.
  All 17 schedule-source tests passed under coverage after this correction.
- `test_expired_signed_decision_is_rejected` failed in fixture setup because a
  reconstructed critic quorum was missing. Its cause is unconfirmed. Both this
  case and the original schedule case passed isolated reproduction under coverage;
  no review quorum, expiry or production control was changed.
- The final combined-gate rerun in `make-check-final.log` ran 3,882 source
  tests in 2,904.336 seconds, with 17 skips and one error in
  `ReviewAcceptanceTests.test_omitted_slot_cannot_shorten_the_tranche` fixture
  setup: the synthetic judge lacked `runtime-count-start.json`. This case passed
  isolated coverage reproduction in 3.982 seconds. The broad-run failure remains
  unexplained; it is not relabeled as a passing run. At that point review source
  and fixtures were unchanged. The fixture replaces container exchanges and
  writes synthetic lifecycle receipts; it does not exercise the native guardian.
- Both original broad runs stopped at the source-test target. Clean-wheel tests, coverage
  reporting, export verification and package targets were **not reached** through
  `make check`. Neither original run established a complete gate pass or a
  releasable candidate.
  The two original logs and three isolated reproductions remain preserved.
- Built local rc.10 native runtime and bootstrap from the frozen dependency set.
  `uv.lock` changes only the project version, and runtime exports are unchanged.
- Actual old installed rc.9 fails the new guardian regression; the new native
  runtime passes readiness, EOF cleanup and a finite deadline with its lease
  writer still open, with no Python/Node on PATH. `/usr/bin/true` is explicitly
  the inert Docker-client fixture for that platform-independent process test.
- Actual frozen-helper probes also refused a 306-second lease and a non-digest
  container ID with exit 2, no readiness byte and no armed/result receipt.
  Neither probe invoked Docker or a provider.
- The retained subscription creator brief was separately verified through the
  unchanged offline Docker image using the **actual new native guardian**.
  The exact snapshot/tests receipt returned and the real container was removed.
  Tests fail as expected against the original unimplemented stub; this is proof
  of baseline execution/cleanup, not implementation or live-workflow acceptance.
- A further real-worker boundary check ran with the host environment stripped
  and PATH set to `/nonexistent`. The same native guardian returned the exact
  snapshot/tests receipt and removed the worker. The first proof's PATH flag
  describes its inert-client fixture; `real-worker-no-python.json` independently
  establishes that property for the actual Docker verification path too.
- Standard standalone archive smoke passed: private installation, credential-free
  setup, both-store exec/recovery, synthetic older-version update/rollback,
  activation recovery, tamper rejection, uninstall/state preservation, and the
  new native guardian checks. Publisher trust is ephemeral for this local smoke;
  production-key qualification remains unrun.
- Local artifact `mos-0.1.0-rc.10-macos-aarch64.tar.gz` SHA-256:
  `102b3b481d998a6f1ca81640f3a1d1f7310940238dbd9dadbf72a26d303a9fea`.
  Native executable SHA-256:
  `51dbd236f882df8b093b29118b53e6f79e67044a41f9cad0ef0e84a262ece6cc`.
  These are local unsigned candidate artifacts, not a published release.
- Evidence is private under `.work/watchdog-verification/`. Its runtime-input
  manifest SHA-256 is
  `0b443a3fc53452ac5ae2b1f24611d4d36fe97941c68295f3dc3dd97d0bcd730e`.
  Native smoke's Git HEAD field is baseline rc.9 because this batch was built
  before commit; the input manifest binds the actual changed rc.10 files. It
  must not be misrepresented as exact-source signed release evidence.

## Source audit and remaining scope

The fixed Linux Git helper already selects its frozen entry. Worker-side Python
launches in coding/reviewer test workers execute inside the separately pinned
Python Docker image, not the standalone host. Update code uses `sys.executable`
for identity, not Python dispatch. Separate conversational live review still
constructs `sys.executable -c ... review-live`; its standalone admission needs
its own correction and qualification before that capability can pass. The
analysis-demo fixture-server launch is also Python-oriented and remains outside
this repair's installed coding claim. Neither is silently marked qualified.

No new subscription/API inference, replacement qualification scope or provider
result alteration occurred. Main's newer dependency changes remain untouched.

## Native evidence and original handoff

| Local receipt | SHA-256 |
|---|---|
| Original-fails/new-passes native guardian and real worker | `6e2b6601180172a8218490c681f0d660141a2f22876d2f87c3a0b0f2486cb417` |
| Real worker with no host Python/Node on PATH | `d026cf8ece2425364d426ab66fcda62c75ef144f640dd23cc7dea518cb0a2b1a` |
| Native invalid-lease refusal | `b01c7894dc797f8a6a93ae9b212ad6706f1a7de774b08a1aea445183b546785e` |
| Standard standalone archive smoke | `5920604d3c67b3332de7aeebaab73145fc1f7cfadd7a1ce05eae8a38da7b8ccf` |

The original handoff left this batch uncommitted because the two full source
gates failed. Those failed logs and the original manifest remain preserved.

## Fixture follow-up and final quality gate

The owner's 2026-10-28 fixture repair request supplied a separate bounded
investigation and concrete correction; see
[Review-conformance fixture work note](REVIEW_CONFORMANCE_FIXTURE_WORK_NOTE.md).
Synthetic review fixtures now share monotonic-derived UTC, keep real subprocess
exchanges, reject elapsed expiry and refuse missing receipts. No production
review authorization or watchdog inputs changed during that follow-up.

The final combined `make check` passed: 3,887 source tests (17 skips), 86%
coverage, runtime-export verification, package builds and 2,862 installed-wheel
tests (13 skips). Ruff/format and full strict Pyright passed. All 12 executable
and test input hashes match the pre-gate manifest. Documentation-only result
updates follow this pass. The fixture work note records final log/manifest hashes.

The tested batch remains on `fix/frozen-watchdog-dispatch` for review.
Exact-source protected signing,
four-target native qualification and fresh installed live-workflow evidence
remain necessary before a release decision. Local unsigned native evidence is
not upgraded to signed evidence by the quality gate. The immutable rc.9 release
and main's newer dependency work remain unchanged.
