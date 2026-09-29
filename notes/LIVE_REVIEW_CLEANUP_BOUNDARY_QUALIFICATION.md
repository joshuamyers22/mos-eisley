# Work Note: corrected cleanup-boundary qualification

- Status: closed
- Owner: Joshua Myers
- Started (UTC): 2026-09-24T00:56:11Z
- Last updated (UTC): 2026-09-24T01:54:47Z
- Review or delete by: G2 closure or the next separately authorized launch review
- Related record: `docs/LIVE_REVIEW_CLEANUP_BOUNDARY_QUALIFICATION_2026-09-24.md`

## Objective and completion evidence

- Intended outcome: finish and assess a wholly fresh three-slot production
  qualification bound to corrected commit `3b32f14` and its exact rebuilt image.
- Required invariants: fixed slots, exact phase/local/observation gates, threshold-two
  quorum, no retries, bounded spend, private evidence, terminal ledgers and worker
  cleanup, with qualification kept distinct from launch authority.
- Completion evidence: three accepted authenticated slots, fresh campaign
  reconstruction, 32,226 micro-USD settled, zero unresolved entries, 12 removed
  workers, and an offline G2/launch-boundary reassessment.

## Context retrieved

- `AGENTS.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, `docs/ROADMAP.md`
- `docs/mos-eisley-plan.md` §26.4, `docs/REVIEW_CAMPAIGN_CEREMONY.md`,
  `docs/REVIEW_LAUNCH_ADMISSION.md`, and ADR-0005
- `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/WORK_NOTE.md`, and the
  existing live-qualification threat model
- Private sealed campaign, completion, observation, lifecycle, ledger, evidence and
  acceptance records; no provider payload or secret was copied into Git

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-24 00:55 | error | Inert host construction passed `preparation_scope` to the wrong contract and stopped before bundle, seal, credential, reservation, worker or provider use | Retained partial private root | Correct harness offline and prepare a wholly fresh campaign |
| 2026-09-24 00:56 | decision | Exact bundle and seal bound commit `3b32f14`, image `3f67fa22…`, three fixed slots and 250,992-micro-USD planned maximum | Bundle `62f23f3f…`; seal `ab71fca3…` | Require exact gates for every live boundary |
| 2026-09-24 01:03 | result | Slot 1 accepted with three completed critics, no findings and 11,644 micro-USD charged | Result `3f6f7f54…`; signed observation `b234761b…` | Continue only after exact observation |
| 2026-09-24 01:07 | result | Slot 2 accepted with two completed critics and one retained `invalid_evidence`; threshold-two quorum held without retry; 10,382 micro-USD charged | Result `866792a2…`; signed observation `51722c50…` | Preserve error and continue only after exact observation |
| 2026-09-24 01:11 | result | Slot 3 accepted with three completed critics, no findings and 10,200 micro-USD charged | Result `a7bf9a30…`; signed observation `9f180401…` | Reconstruct the complete campaign |
| 2026-09-24 01:13 | result | Independent repository verification accepted all three slots; all ledgers were terminal and all 12 workers were absent from Docker | Evidence `fde095a1…`; result `0a276558…` | Reassess G2 and stop before any further live call |
| 2026-09-24 01:16 | decision | G2 qualification exit is satisfied; production launch remains a separate current-authority boundary | Plan §26.4 and launch-admission contract | Document, run offline gates and commit |
| 2026-09-24 01:55 | check | Ruff and Pyright passed; the 2,431-test source run was clean except for 31 restricted-sandbox loopback-bind errors, and all 68 isolated MCP tests passed with localhost permission | Repository checks and MCP rerun | Commit the documentation-only reassessment |

## Handoff

- Current state: G2 live read-only qualification is complete for the exact commit and
  image. No content finding or required change remains from this campaign.
- Next smallest safe action: complete G3's offline real-input prerequisites, or—only
  on new owner direction—prepare a fresh exact launch proposal without dispatch.
- Blocker and required authority/input: any production target call needs a current,
  separately signed launch decision, fresh ledger and exact phase/local approvals.
- Checks already run: source/image verification, exact bundle/seal hashes, per-slot
  result/observation/lifecycle inspection, fresh campaign reconstruction, ledger and
  Docker cleanup inspection, clean-commit check, Ruff, Pyright, the 2,431-test source
  suite, and the 68-test MCP rerun with localhost permission.

## Close and promote

- Outcome and verification: campaign accepted with three qualifying attempts and
  32,226 micro-USD settled; no retry, unresolved entry or remaining worker.
- Durable fact promoted to `PROJECT_MEMORY.md`: G2 qualification is complete while
  production launch remains separately gated.
- Decision promoted to documentation: the current campaign closes historical Q-011
  but grants no launch, retry, routing, provider-authorship or billing authority.
- Regression evidence: `tests/test_review_campaign_dispatch.py`, the retained
  campaign reconstruction, and the isolated MCP verification recorded above.
- Temporary artifacts removed: none; private campaign and inert partial evidence are
  intentionally retained for audit.
