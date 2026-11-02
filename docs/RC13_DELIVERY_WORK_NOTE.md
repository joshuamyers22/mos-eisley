# rc.13 diagnostics delivery and one-call qualification

- Status: closed, authorized delivery complete. Owner Joshua Myers; operator
  Codex. Started 2026-10-31 UTC; completed 2026-11-01 UTC.
- Authority: finish/review/merge PR #353, freeze rc.13, protected signing,
  affected signed installation/upgrade/offline diagnostics, then one fresh bounded
  Claude diagnostic invocation. Keep rc.12's uncertain call and all prior evidence
  closed. This explicit new task supersedes the earlier implementation-only
  work note's no-new-call scope; it does not authorize a full live campaign.

## Guidance, invariants and review

Use repository Python engineering, bounded verification and adversarial review
guides; work-note, threat-model and verification-loop templates. Review exact
PR #353 initial head `7b62c02533364d202c6cc55d9cbdc29d98fd391e` and its
qualification-observer correction `01a4af2` against the initial 860-input
full-gate manifest, fixed metadata schema, private writer, limits, cancellation,
cleanup and uncertain-ledger tests. Author/operator overlap is disclosed; this
technical review is not independent human security approval. The owner has
explicitly authorized normal merge after CI and review. Protected signing remains
an accountable owner gate; publication approval is outside this request.

Keep rc.12's dependency lock/export set frozen for the release, changing only the
project version to rc.13. Main retains its newer dependencies. Preserve candidate
ancestry in main before tagging; never retarget an immutable tag or asset. Enrolled
signature/bootstrap/archive/state/recovery/rollback predicates remain strict.
The exact published rc.11 and rc.12 predecessors join the existing seven release
workflow predecessors. Signed offline diagnostics use fake shell clients with
private HOME and no provider connection or host Python/Node on child PATH.

Threats: substitution, stale approvals, native text leaking into progress,
unbounded/repeated dispatch, uncertain-call replay and misleading qualification.
Use exact source/tag/run/artifact identities, private exclusive attempt files,
the fixed capped progress model and no raw payloads in tracked documentation.
No signing-key reads, credential-cache reads, API fallback, credit purchase,
model substitution, increased timeout or automatic retry is authorized.

## Budget and stopping rules

One combined candidate and main integration batch, focused contracts then one
full gate per dependency set (four-hour ceilings), and required CI before normal
merge. Do not run the two local full suites concurrently. Protected release
preparation and all four signed jobs must pass before dependent live work.
Review all reports, source/epoch/hash bindings and exact predecessor identities.
Do not approve protected publication as part of this qualification.

After signed installation and offline progress review, one fresh Claude native
diagnostic scope: critic_anthropic, Claude Code 2.1.283, Sonnet 5/high, maximum
one invocation, 60-second native deadline, 128,000 canonical input bytes, 16,000
text output bytes, 8,192 reported output tokens and a fresh finite grant. Actual
HOME and native credential selection remain unchanged for this real call;
API keys are absent. Preserve the rc.12 synthetic implementation-review request
as a read-only diagnostic input with exact hash binding; a new grant/usage root
cannot complete or resume the old slot. Host orchestration from the exact frozen
candidate source is disclosed separately from installed offline binary checks.
Native billing/internal retries remain unverified. Stop after that call regardless
of success; stop on any earlier unplanned signature, build, CI, test, privacy,
recovery or cleanup failure. No replacement scope, renewal, response repair,
failed-session replay or broad installed live-workflow acceptance follows.

## Evidence and handoff

PR review/CI, frozen candidate, integration, tag/run, four-platform reports and
the single diagnostic outcome remain pending. Preserve all original evidence;
ordinary engineering records do not establish prospective evaluation eligibility.
No sampling registry, custodian mapping, label or outcome store is consulted.


Preparation observations (2026-11-01 UTC): initial PR #353 CI passed full source
and wheel suites but found a separately typed qualification observer using the
old reader signature. The corrected observer passes 19 offline tool cases and
strict typing; current-head CI is pending. The rc.13 source adapter and its test
also retain rc.12's SDK-1 constructor, since main's SDK-2 telemetry keyword is not
supported by frozen Anthropic 1.13. Main integration must preserve its SDK-2
adapter/test plus dependency files. Seventy-three focused candidate contracts,
Ruff/format, strict source typing and explicit qualification-tool typing pass.
The new signed progress tool uses four shell fixtures, disables updates, and
checks source/version/signature/archive/bootstrap bindings, fixed redacted
receipt shape and same-attempt refusal before producing a report. The expanded
protected run should yield 50 reports and 67 candidate assets; these are expected
counts until actual evidence review, not successful qualification claims.

Technical review of corrected PR #353 is complete, pending required CI. The
application, dependencies and source-test hashes match the completed initial
full gate; only the two explicitly revalidated qualification-tool files differ.
Review traced fixed-field metadata construction, pre-cleanup snapshots, bounded
streams, private exclusive writes, cancellation, uncertain-use and no-replay
paths, including the corrected init observer. No remaining blocking technical
finding was identified. This is author/operator technical review under the
owner's explicit merge instruction, not independent human security approval.
No provider inference or publication approval was used for the review.

PR #353's corrected head `01a4af23a6dbdee2b6a2e6926e5af19ea4448d00`
passed all 13 checks and merged normally as
`c41576575f85784abfc1456b13954f828a705a26` at `2026-11-01T15:14:15Z`.
Its merge tree equals the reviewed head. Step 1 is complete.

The candidate source suite passed 3,911 tests in 2,885.503 seconds (17 skips),
at 86% coverage; static checks, export verification and build also passed.
The unfinished wheel stage crossed the declared four-hour wall-time ceiling
across an overnight gap: 51,544.665 observed wall seconds versus the controller's
4,795.904 monotonic seconds. The precise cause of that discrepancy is not
established. The monotonic-only controller did not enforce the wall limit.
The verified owned make group was stopped; its controller and captured
subprocesses were then confirmed absent. Original result remains exit -15,
all 862 application input hashes unchanged, log SHA256
`3581fda5802b116a7326d5492c883ba859c2e65dfafac2c2733a3822ef9e24be`.
That full invocation is not reported as passing.

Only the complete unfinished installed-wheel stage is being rerun with fresh
private temporary state and the identical built wheel/source. Its controller
checks both wall and monotonic 90-minute limits. Passed source/static/build
checks are retained, not repeated. Main integration's forthcoming full gate also
checks both clocks against its four-hour ceiling. The original evidence remains
unchanged. Candidate commit/tag/signing and actual provider dispatch remain
pending the required passing evidence; no inference or new live grant has run.


The first fresh wheel retry finished with one import error: the new qualifier
helper had not been copied into the isolated wheel-test fixture. Its log remains
retained (SHA256 `050eb05528fd30c543ff0382f643f0ec10703d2048e34b6a175e04db3122d1bf`).
The correction adds that helper to the fixture bundle only. All application,
dependency and source-test inputs remain unchanged; the sole revised quality
input is `tools/smoke_package.py`. Three focused cases then passed in a clean
installed-wheel environment with source-package fallback excluded. Build artifacts
were refreshed; the runtime wheel stayed byte-identical.

The complete corrected wheel stage passed 2,898 tests in 2,174.420 seconds,
13 skips, exit 0. Its wall and monotonic elapsed times were both about 2,198.9
seconds, within the new 90-minute limit. Final log SHA256:
`d0a3193d9fb3f41ae81df1a9f24c3f7aedd7c9b43fad5f3be5b665d5d026573f`.
All 416 runtime Python files in the wheel match source. Final 862-input names and
hashes remain unchanged, and all required stages now pass after the disclosed
wheel recovery. The original interrupted full invocation and first failed wheel
retry are preserved, not relabeled. Runtime wheel SHA256:
`e28410bdfa2fb942c3fa05b67a01433d231681af22ca7430af2d1f6c92862492`.
The frozen dependency lock/export and SDK-1 adapter/test match rc.12 exactly apart
from the project's own version. No provider inference has occurred.


Candidate frozen at `8c7690733af1bbc4861911d2c0a2a516961985da` and pushed
to `fix/rc13-native-progress-candidate`. The main integration retains main
SDK-2 dependencies, runtime export, adapter and tests; only its own package
version changes to rc.13. All five preservation comparisons passed.
Integration focused checks passed 74 tests, Ruff, formatting, project typing
and explicit qualification-tool typing. A single combined full integration
gate now runs with both wall and monotonic four-hour ceilings. No native
provider inference or new live authorization has occurred.


The combined main integration `make check` passed, exit 0: 3,912 source
tests in 2,890.446 seconds (17 skips, 86% coverage), and 2,899 isolated
installed-wheel tests in 2,033.119 seconds (13 skips). Total wall time
4,985.357 seconds, within the four-hour ceiling. All 862 input hashes remain
unchanged, and the five main dependency/adapter preservation comparisons
passed again before commit. Full log SHA256:
`8bf425dee4714a8d82f0d5f2cdbac34dd983c7f1b57fba4adff1a3933e30a1aa`.
Required integration CI, main merge, exact-candidate tag/signing, signed
qualification and the one fresh diagnostic call remain pending.


## Closeout, 2026-11-01 UTC

[The final qualification review](RC13_QUALIFICATION_REVIEW.md) records all four
completed steps. Integration PR #354 passed all 17 checks and merged normally
as `0603949`; the exact frozen `8c76907` tag remains an ancestor of main.
Protected run 41342968889, attempt 1, passed signing and all four signed jobs.
Strict review passed 50 reports and 67 assets, including four progress matrices
and four actual rc.12 upgrades. The owner separately published immutable release
430907808 at 22:43:52Z; its complete inventory and attestation verified. Operator
approval covered preparation/signing only, never publication.

The signed macOS arm64 installation matched its qualified native hash and disabled
updates. Fresh installed Claude readiness preceded one new finite authorization.
The exact-source host-orchestrated diagnostic completed in 55.84 seconds at
22:46:33Z, one reservation/dispatch/completion, no retry or API fallback. Its
synthetic critic decision was `accept`. Success produces no failure-progress
receipt; offline signed tests qualify that path. All 121 old rc.12 campaign files
outside nested Git internals and all candidate/harness inputs stayed unchanged.
No historical cause, old uncertain completion, full coding/integration campaign,
SQLite live acceptance or broader readiness is claimed. The one-call task stops
here; any full installed live-workflow campaign requires fresh authority.

Durable facts are indexed in `PROJECT_MEMORY.md`; the README identifies the
published preview and remaining acceptance gap. This closeout changes documents
only; documentation/link, evidence identity and diff checks apply. No provider
call is rerun for documentation validation.
