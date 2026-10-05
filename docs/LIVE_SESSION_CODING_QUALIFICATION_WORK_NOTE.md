# Work note: budgeted live session coding qualification

- Status: all four requested functional live scenarios passed; final cancellation
  charge reconciled; accountable release review tracked separately.
- Owner: Joshua Myers authorizes operation; Codex executes and records evidence.
- Date: 2026-10-05.
- Qualified runtime candidate: `44adf471e7386f34fb37479b46eaf0b2302d4291`.
- Historical candidates: `d7d203b`, `b9a0c30`, `d2ca0c3`, `f1c9145`.
- Guidance: repository Python engineering and agentic verification guides,
  `templates/WORK_NOTE.md`, `templates/THREAT_MODEL.md`; current GitHub template
  provenance is recorded in `LIVE_SESSION_CODING_WORK_NOTE.md`.

## Final functional results

All cases used ordinary plain CLI sessions with SQLite persistence, real live
OpenAI/Anthropic role responses and the same committed runtime candidate. The
final roster is Sol/medium creator, Luna/low child, Terra/low and Sonnet 5/low
critics, Opus 5.5/low judge. Each session consumed one ordinary implementation
exchange; no goal, fork or task budget was introduced.

| Required scenario | Verified result on `44adf47` |
|---|---|
| Successful implementation and verified integration | 10 calls; source-only commit `fd70c0aacf4aab72cccf331ebf31868771e9fd8b`; frozen tests passed before and after integration; protected tests unchanged |
| Failed tests followed by bounded correction | 11 calls; diagnostic candidate failed real tests, one correction passed the identical frozen package; reviewed and approved source-only commit `20c9c7cf48ca9fd32940019f334cd582972d79b4` passed fresh final verification |
| Rejected review prevents integration | 4 calls; judge requested revision of the impossible task; no child dispatch, integration marker or Git change |
| Cancellation and resume without duplicates | Cancelled after real Git staging and separately while a provider reservation was held; cold resumes preserved ledger entries/charges, Git source/tests/refs and model artifact file hashes; saved entries stayed cancelled with one consumed exchange |

The staging-cancellation case made 10 calls; its owned detached worktree was
removed and integration never started. Held-charge cancellation admitted one
creator call and preserved its entire **113,000 micro-USD** uncertain allowance.
This proves cancellation while a reservation was held, without claiming that
provider generation had started. Neither cold resume dispatched a new call.
Every Docker lifecycle created by the five final scopes has a removal receipt.

Exposure at functional completion: **2,466,033 micro-USD ($2.466033)** under the unchanged $10 cap:
2,353,033 settled and 113,000 uncertain, across 132 entries and 23 paid attempts.
The audit matched every retained role receipt to its exact ledger entry and
reservation, including the reconciled historical receipt. All superseded and
failed attempts remain represented; none is counted as a passing required case.

Private evidence root:
`/Users/josh/.mos-eisley-live-session-qualification-2026-10-05`.
Completed functional evidence SHA-256:
`29601e6aef36147aa08f7b4c241ea16d244162af3195b6de1da51512ba1940d0`.
The final correction scope is `correction-sol-v3-concise`; the other final scopes
are `success-sol-v3`, `rejection-sol-v3`, `cancellation-stage-sol-v3` and
`cancellation-sol-v3`. Their selection and verified-evidence hashes are bound in
that aggregate. Raw packets remain private and outside sampling artifacts.

Affected source and installed-wheel verification both passed 19 tests, including
large review packets with exact artifact identity through integration. Ruff,
format checking, Pyright, dependency-export verification and source/wheel builds
passed. The installed wheel's two changed workflow modules match the committed
runtime bytes. Wheel SHA-256:
`4844c847ffd4d04d6be98025abcd6b31017a1666d62aee0894c48b213cfa53b9`.
Earlier broad verification and its limits remain in the implementation work note.

The [release work note](LIVE_SESSION_CODING_RELEASE_WORK_NOTE.md) records the
subsequent accountable adjustment of the cancellation charge to 22,624 micro-USD,
using a complete provider export and Joshua's explicit usage-scope attestation.
Current total is **$2.375657**, all 132 entries settled and zero unresolved charges.
The original uncertain receipt and functional completion evidence remain unchanged.

This completes the requested bounded functional demonstration for existing-source
`pure_python_v1` coding. The one-unresolved-entry admission limit remains enforced.
Accountable review of the
new paid-call/integration composition and release approval remain required. This
does not qualify general repositories, goals, forks or prospective evaluation.

## Objective and acceptance evidence

Use ordinary CLI sessions with the existing qualified provider routes to exercise
successful verified integration, failed tests followed by bounded correction,
rejected review preventing integration, and cancellation with cold resume without
duplicate provider calls or Git writes. Each scenario uses a separate tiny synthetic
Git repository. Inspect actual frozen test receipts, review decisions, integration
markers, saved session state and ledger entries. No model outcome is replaced.

The correction exercise requests a deliberately failing first candidate followed
by correction against unchanged real tests. This is a declared controlled fault,
not evidence of a spontaneous model failure. The rejection exercise supplies
contradictory requirements; only an actual rejected review counts. Failure to
obtain a required outcome is reported, not relabeled as success.

## Scope, threats and stopping rules

- User-authorized total exposure: **$10**, including held/uncertain charges, in one
  fresh immutable shared ledger. Never reset, top up or refund it automatically.
- Final existing routes: Sol/medium creator, Luna/low child, Terra/low and Sonnet 5/low
  critics, Opus 5.5/low judge. Fresh schema-2 prices checked against official
  provider documentation; exact model/effort selection, no substitution. Historical
  attempts used Astra/high before the explicitly recorded Sol campaign.
- Maximum 9,000 input and 3,400 output tokens per role call, zero SDK retries;
  one correction cycle, at most 15 calls and 600 seconds per workflow.
- All task files are synthetic. Keys load only from an owner-private file outside
  Git into host subprocess environment. Raw requests/results stay in private
  artifacts, never in this note or sampling artifacts.
- Image fixed to
  `sha256:11023d7c1443bdb03365e3eb93bd29f59c6da5b5e3333f762e0db33a89ea9763`.
  Worker has no credentials/network/mounts; trusted host alone integrates source.
- Protected tests and source identity must remain exact. Review rejection stops
  integration. Existing attempt markers prohibit replay. Run cancellation last
  so an uncertain hold cannot disrupt preceding scenarios.
- Stop on credential failure, uncertain transport, ledger violation, altered
  candidate, expired selection, unowned paths or exhausted budget. Preserve
  evidence rather than retrying an uncertain request.
- This campaign does not grant release approval or qualify arbitrary repositories,
  goals, forks, empirical routing or prospective evaluation evidence.

## Observations

Credentials file exists with mode `0600`; no secret was displayed. The immutable
local worker image was inspected successfully. Previous source/wheel and unpaid
Docker/Git checks remain documented in the implementation work note.

## Handoff

The first ordinary success session settled one Astra creator call at 68,270
micro-USD. Its result used arrays for three fields whose contract requires strings;
the session stopped before child dispatch, baseline execution or integration.
The original candidate therefore failed this qualification attempt. Clarifying
those field types in the creator prompt is a source correction; qualification
must restart against its new committed candidate, retaining the first attempt
and charge in the same shared ledger. No provider result is repaired or replayed.

Candidate `b9a0c30` completed the success exercise with ten settled live role calls,
protected tests unchanged, source-only integration and fresh final test receipt.
The first correction scope failed during baseline execution: 441 generated test
cases exceeded the worker's 32,000-byte output cap (confirmed by an unpaid replay).
Its one bounded replacement stopped after the Sonnet critic returned acceptance
with nonempty findings, violating an unstated validator invariant. The Terra
critic also identified ambiguity between the worker's single-invocation allowance
and the host's two-candidate correction budget. No correction child or integration
occurred. Aggregate settled charge at that point was 498,721 micro-USD.

The next source candidate supplies each role's JSON schema, states the review
decision/findings invariant, and binds phase and actual cumulative workflow bounds
into the reviewed artifact without disclosing author history or model identities.
Creator instructions also describe private test retention, review/integration
ordering and the worker output cap. A regression assertion checks that independent
review sees both the true host bounds and the separate worker invocation allowance.
All four scenarios must run against this next commit; earlier attempts stay in the
shared ledger and evidence. No further replacement of the failed `b9a0c30`
correction exercise is authorized by the campaign's own stopping rule.

## Historical candidate outcomes before reconciliation

Candidate `d2ca0c374c622bd90b02c0b434e15a65562ced85` passed the live success
scenario through a plain ordinary CLI session and SQLite persistence. Ten role
calls settled. Integrated source-only commit
`53585f94e12a1d5a7fdc024c4619d6651d160f7d` passed frozen tests before and after
integration; existing test content stayed unchanged. Four Docker lifecycle
receipts record removal. The saved implementation entry is completed and consumes
one ordinary session exchange. Lint, type checking with the project interpreter,
and all 18 focused workflow tests passed after the source corrections.

Its first correction attempt stopped at a generic baseline broker exchange error.
The same small frozen test package returned a valid failed-test receipt in unpaid
local verification, direct offline image execution, and an exact Docker broker
replay. The original broker error was not reproduced; its cause remains
unconfirmed. This is a material operational limitation, not a passing correction
scenario. A recorded campaign amendment permitted one fresh correction attempt
after those diagnostics, preserving all previous evidence and charges.

That fresh attempt reached the 60-second exchange deadline without a usable
provider response. Its original uncertain receipt retains **282,500 micro-USD**.
The existing live transport admits at most one unresolved ledger entry; this hold
prevents further role dispatch even though the monetary ceiling has remaining
capacity. No refund, reconciliation, new ledger or retry of that request occurred.
The failed exchange ran approximately **20:16:17–20:17:17 UTC on 2026-10-05**.

Cold resume of that saved failed session opened and saved successfully. Before and
after snapshots prove identical ledger charges/entries, Git source/tests/refs, and
private model artifact file hashes. The saved entry remains failed with exactly
one consumed exchange. This establishes no automatic replay after an uncertain
failure; it does not establish the requested deliberate cancellation scenario.

| Required scenario | Historical result on `d2ca0c3` |
|---|---|
| Successful implementation and verified integration | Passed |
| Failed tests followed by bounded correction | Incomplete; stopped before coding-child dispatch |
| Rejected review prevents integration | Not dispatched after the unresolved hold |
| Deliberate cancellation and resume without duplicate calls/writes | Not dispatched; uncertain-failure cold resume separately verified |

Total accounted exposure: **1,150,531 micro-USD ($1.150531)** across 27 ledger
entries: 868,031 settled and 282,500 uncertain. The original authorized ceiling
remains 10,000,000 micro-USD. All seven paid attempt dispositions are retained,
including earlier candidates and the failed fresh attempt.

Private evidence root:
`/Users/josh/.mos-eisley-live-session-qualification-2026-10-05`.
Aggregate evidence SHA-256:
`a1e4681fb82fd5cff3ba34960cde8d3ec7023d7f4f2ba01354a2848564a841e3`.
Raw model packets stay private and are not copied into tracked or sampling
artifacts. No claim of prospective evaluation eligibility or release readiness
follows from this campaign.

## Historical reconciliation handoff and amendments

### October 5 reconciliation and Sol campaign

The complete October 5 OpenAI CSV, together with Joshua's explicit confirmation
that all credential usage is included and only qualification used Astra, identifies
one unmatched Astra request: 925 input and 2,324 output tokens, no cache writes.
The original 282,500 micro-USD hold was reconciled to 125,450 micro-USD. Its original
uncertain receipt remains unchanged; replaying the same reconciliation was inert.
The authority is the authenticated owner session attestation. A local executor
integrity seal is not represented as an independently enrolled human signature.
After reconciliation the ledger contained 993,481 micro-USD and no unresolved entries.

A fresh predeclared campaign selected qualified Sol/medium as creator, retaining
the same other routes, exact `d2ca0c3` source, worker, ledger and $10 cap. Success
passed ten live calls with source-only commit `67ed882848b26b4c40a63cc9e9cf9b6410a6cef2`
and fresh final frozen tests. Correction stopped at another baseline broker error;
one exact unpaid replay and eight bounded diagnostic exchanges returned valid
failed-test receipts. The original error remains unconfirmed. Rejection did not
pass: critics/judge accepted a plan explaining the impossible requirements and
creator approval allowed child dispatch. No integration occurred. Stage
cancellation did not reach staging: creator approval misread the offline allowance
as cumulative workflow authority and requested revision.

The next source correction makes plan acceptance explicitly authorize feasible
coding-child dispatch, requires revision for an impossible/stopping plan, and gives
creator approval the same phase and budget interpretation as critics/judge. The
existing regression now checks approval receives the same bound reviewed artifact.
No original result is replaced; all four scenarios must restart against the next
committed candidate. The held-call cancellation scope has not been dispatched.
All 18 focused workflow tests, Ruff and Pyright with the project interpreter passed
for this correction. The repository uses unittest discovery; initial pytest and
direct module invocations did not load the suite and are not passing checks.

The following historical next-step text described the previous blocking hold;
that reconciliation is now complete:

Obtain independent provider request/billing evidence and accountable reconciliation
of ledger entry
`0bafa5d29f1784ab94e3af290efea2986fbd26918bca7d2f41fbbb3f16316b40`
under ledger
`553abb8dfd706b2535cc79fa3303a0aa80bf1835c032d86958671d6c24a2d99d`.
Preserve the full hold until that workflow verifies evidence and authority. Then
prepare fresh, explicitly bounded remaining scenarios against the corrected
runtime candidate with current policies and the same total authorization. Resolve
or document the broker failure in accountable review before release claims.

### Packet-size diagnosis and correction

On `f1c9145`, success passed ten live calls with source-only commit
`eb2d803f699a47fcd43c3909126b3da642122522`. Rejection passed four calls: the
judge requested revision, no child was called and no Git state changed. Deliberate
cancellation after real Git staging passed ten calls: integration never started,
the saved entry is cancelled, its owned worktree was removed, and cold resume
preserved ledger, Git and private artifact snapshots with one consumed exchange.

Correction again stopped before the first critic. An unpaid replay of the complete
workflow using the stored plan stopped at a `TextBlock` validation error: the
review packet exceeds its 8,000-character block cap. This reproduces the host
failure after successful baseline verification. Earlier attribution of this stop
to Docker was incorrect; a generic public error and absence of a persisted
baseline receipt were insufficient evidence of its stage. Stored responses used
in this diagnostic are not live qualification outcomes.

The next correction chunks role packet text into consecutive blocks of at most
8,000 characters, tells the model to concatenate them in order, and preserves the
exact packet, artifact digests and existing cumulative byte/token/cost bounds.
A large-plan regression verifies exact artifact identity reaches both critics,
judge and creator approval through real fixture Git integration. No blocked role
call or failed session is replayed. Requalification must use fresh ordinary sessions
against the next committed candidate; previous receipts remain immutable.
The affected unittest suite passed all 19 tests, including the new large-packet
regression. Ruff and Pyright passed for the changed implementation and tests.

### Final fixture amendments

On `44adf47`, the first correction scope integrated correctly on its first candidate;
the failed-test correction criterion was not exercised. A fresh previous-field
guard scope requested a diagnostic return of 0, but that matched its initial
source exactly; the host rejected the unchanged patch before execution. A fresh
changed-baseline scope stopped because the child supplied a stale before-content
digest and skipped the diagnostic. These are retained failures of qualification
criteria, not repaired model responses or passing correction cases.

The final bounded fixture amendment restored the original return-0 base, requested
a distinct diagnostic sentinel of -999, and asked for a concise plan explicitly
conditioned on `previous={}` versus host-supplied failed-candidate evidence. Real
live responses produced the required failed first candidate and passing correction.
The host never supplied a patch, changed a model response, weakened tests or
replayed an uncertain call. Final success, rejection and both cancellation scopes
then ran against the identical `44adf47` candidate. The held-call cancellation was
last; no paid call followed it.
