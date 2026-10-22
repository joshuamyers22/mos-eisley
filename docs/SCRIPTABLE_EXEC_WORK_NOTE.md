# Scriptable execution verification

- Status: closed
- Owner: Joshua Myers
- Started and last updated (UTC): 2026-10-21
- Review or delete by: 2026-11-04; remove after merge evidence is retained
- Related requirement: `mos-eisley-plan.md` §31.3

Owner: Joshua Myers. Baseline: `b0490655`. Scope: plan §31.3 and the five
user-requested stdin, JSON, exit-status, shared-controller and installed-wheel
acceptance criteria. Material change; no new execution, publication or provider
authority. Guides: `PYTHON_ENGINEERING_GUIDE.md`, `AGENTIC_VERIFICATION_GUIDE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md` and the production-template release checklist.

Blocking rubric: strict bounded UTF-8 and ambiguous-input rejection before startup;
one versioned terminal record per invocation with usable stdout; explicit review
verdict and unknown-usage/omission markers; unchanged conversation policy, storage,
ledger and cancellation ownership; source and installed-wheel failure journeys.

Verification budget: three evidence-changing passes (focused contracts, installed
subprocess journeys, combined repository gate), up to four hours, zero provider
spend. Stop on passing gates or report an external blocker; never relax policy to
pass. Revert the coherent change to roll back. Actual credentialed live execution
and release approval remain separate from synthetic engineering verification.

Failure model: oversized/invalid/piped input, accidental slash execution, malformed
arguments, provider failure, incomplete critic quorum, cancellation during input
or dispatch, persistence failure, and closed output pipes. Preserve consumed
attempts and uncertain ledger charges; never automatically retry.

## Evidence

- Focused source suite: 14 tests passed, including real console subprocesses on
  snapshot/SQLite, exact Unicode byte boundary, ambiguous/malformed input, literal
  slash text, failed providers, complete/incomplete reviews, interrupted stdin,
  repeated-signal controller cleanup, lost completion acknowledgement and closed
  stdout. No credentialed provider calls.
- Fresh wheel: built wheel/sdist, installed the 42 hash-locked runtime packages
  offline into a fresh virtual environment, installed the wheel without source
  dependencies, verified its import resolves beneath the isolated environment,
  copied only `test_exec.py` outside the checkout, and passed all 14 tests again
  through the installed `mos` entry point.
- Live-review regression suite: all 11 tests passed, including an actual child
  process whose diagnostic output was routed to stderr. Existing launch inputs
  and retained-result checks remain in place.
- Final affected-file strict typing: zero errors/warnings. Lint, formatting and
  whitespace checks pass. Typed resource-limit exceptions preserve existing
  `ValueError`/`ProviderError` compatibility and do not alter spending arithmetic.
- Final spending regressions: 23 OpenAI spending, 16 ledger and 9 batch-ledger
  tests passed after the final typed-error changes (48 total).
- `make check` completed with exit zero: lint/format, strict typing, 3,775 source
  tests (17 existing skips), 85% total coverage, dependency-export verification,
  wheel/sdist builds and 2,744 installed-wheel tests (13 existing skips). Native
  or platform-specific skipped checks are not qualification evidence.

The focused passes found and corrected a structured fingerprint incorrectly used
as a string digest, a test ledger fixture using the wrong contract, and Python's
closed-stdout final flush changing the exit status. Their regressions now pass.
Later code changes received affected checks while the full source suite ran;
installed-wheel verification uses the final implementation. These are engineering
checks, not independent security approval or live/release qualification.


## Close and promote

Stop reason: passed. All five requested contract dimensions have passing source
and installed-package evidence; no blocking implementation finding remains.
The combined repository gate ran once; subsequent changes received affected checks
and the final wheel smoke suite. No paid calls, release, merge or publication was
performed. Live operating approval and the existing platform/release gates retain
their prior scope.

The durable interface contract is in `SCRIPTABLE_EXEC.md`; regression evidence is
in `tests/test_exec.py` and `tests/test_conversation_live_review.py`. Project memory
contains the stable `conversation.scriptable-exec` entry, and the roadmap records
implementation status. No ADR is needed for a renderer over the approved existing
controller. Disposable isolated wheel environments were removed automatically;
ignored development/build outputs remain available for local review.
