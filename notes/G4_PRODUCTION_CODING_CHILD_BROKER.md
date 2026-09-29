# Work Note: G4 production coding-child broker

- Status: offline implementation and package verification complete; live/release gated
- Owner: Joshua Myers (decision); Codex (implementation and self-review)
- Started / updated (UTC): 2026-09-24
- Review or delete by: retain with G4 delivery evidence

## Objective and completion evidence

- Outcome: compose a distinct signed, exact-offer provider grant with a one-use
  isolated broker, conservative shared-ledger reservation, provider-usage
  settlement, enrolled-child signing and durable replay.
- Invariants: no provider call under the offline dispatch grant alone; no tools,
  source/Git writes, retry, spending release on uncertainty or final acceptance.
- Acceptance: fake-transport success/failure/replay/duplicate negatives, prior G4
  correction regressions, strict static checks and combined repository gate.

## Context retrieved and guidance selected

`AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, roadmap G4,
plan §§14.2.1, 15.7 and 26.2; existing correction dispatch/integration,
provider broker, spending ledger, audit and OpenAI transport source/tests.
Selected pinned guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
`templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, `templates/WORK_NOTE.md`.
The OpenAI Docs skill selected the official Responses migration reference for
stateless `store=false`, typed output and tool-free request behavior; no local
credential helper was available and no provider credential was accessed.

## Boundary, budget and stopping rules

- Risk: high — private code/test transfer, creator/child signatures, credential
  boundary and spending ledger.
- Ceiling: two evidence-changing passes, one combined gate, zero live calls/spend.
- Stop on signature/request drift, stale source, invalid price/count/response,
  duplicate grant, expired policy, nonprivate store or need for owner approval.
- Rollback: uncommitted source/docs can be reviewed or reverted by the owner;
  no live ledger/call state was created.

## Observations and attempts

| Time (UTC) | Type | Observation / result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-24 | observation | Offline dispatch had only injected proposal source and child-reported usage; production broker absent. | `reviewer_correction_dispatch.py`; G4 docs | Add separate signed provider/spend boundary |
| 2026-09-24 | implementation | Exact offer preview, creator grant, isolated one-use request, conservative reservation and measured proposal signing added. | `reviewer_coding_broker.py`; focused tests | Replay and negative checks |
| 2026-09-24 | verification | Fake transport covered success, malformed answer, duplicate signed grant, offer drift, uncertain send and replay tamper; no live call. | `tests/test_reviewer_coding_broker.py` | Combined gate |

## Handoff

- Current state: permissioned `make check` passed (2,487 source tests, four
  skips, 88% coverage; build and 1,834 wheel tests). After adding the broker
  file to installed-wheel smoke, `make smoke` passed 1,841 tests. The linked
  verification record retains the exact distinction between these runs.
- Next safe action: accountable review and separate exact live-call authorization
  only if the owner chooses; then renewed correction chain and final whole suites.
- Blocker: code existence is not live authorization or final G4 approval.
- No provider credential, source transfer, call, external write or cost occurred.
