# Work note: budgeted live session coding qualification

- Status: preparation; no live outcome yet.
- Owner: Joshua Myers authorizes operation; Codex executes and records evidence.
- Date: 2026-10-05.
- Candidate: `d7d203b`, source and runtime code remain pinned.
- Guidance: repository Python engineering and agentic verification guides,
  `templates/WORK_NOTE.md`, `templates/THREAT_MODEL.md`; current GitHub template
  provenance is recorded in `LIVE_SESSION_CODING_WORK_NOTE.md`.

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
- Existing routes: Astra/high creator, Luna/low child, Terra/low and Sonnet 5/low
  critics, Opus 5.5/low judge. Fresh schema-2 prices checked against official
  provider documentation; no model or effort substitution.
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
