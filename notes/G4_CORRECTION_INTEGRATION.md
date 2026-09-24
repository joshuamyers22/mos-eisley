# Work Note: G4 isolated correction integration

- Status: closed for the offline slice; production release gated
- Owner: Josh Myers (decision); Codex (implementation and self-review)
- Started (UTC): 2026-09-24
- Last updated (UTC): 2026-09-24
- Review or delete by: retain as G4 delivery evidence

## Objective and completion evidence

- Outcome: commit one signed correction proposal only in an isolated, private
  worktree under a new creator approval and task/cycle-unique claim.
- Invariants: original checkout unchanged; no test/path substitution, hook/filter
  execution, provider call, merge/push, retry or acceptance.
- Acceptance: focused negative/positive tests, lint/typing, full repository gate,
  build/smoke where available, and an explicit release caveat.

## Context retrieved

`AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, roadmap G4,
plan §§11, 14.2.1, 15.7 and 26.2; the prior G4 correction/dispatch contracts,
source and tests. Selected pinned guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
`templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, and
`templates/WORK_NOTE.md`.

## Boundary and stopping rules

- Risk: high, because trusted Git writes shared object/worktree metadata.
- Resource ceiling: one offline implementation batch, two evidence-changing
  verification passes and one `make check`; no provider or live calls.
- Stop on unsafe Git tree/config, stale source, failed claim, unexpected diff,
  dirty worktree, unsigned evidence, or need for production authority.
- Independent production sign-off remains a separate gate.

## Handoff

- Current state: offline integration boundary implemented and locally verified.
- Next smallest safe action: separately design the measured production coding
  broker and later renewed/final G4 gates; do not activate this offline slice.
- Blocker: production use requires accountable approval and remaining G4 gates.

## Close and promote

- Permitted `make check` passed: source suite and 88% branch-inclusive coverage,
  export/build, and 1,834 installed-wheel tests. The sandboxed attempt had 31
  MCP localhost-bind permission errors; it was not a code pass.
- Final full original-checkout status and private-store checks followed that aggregate gate.
  Focused 2-test integration suite, lint, typing, export and build passed after it;
  the entire aggregate gate was not repeated for this final one-line check.
- Durable contract and threat decisions: `docs/G4_CORRECTION_INTEGRATION.md`,
  its threat model, architecture review and verification record.
- No live/provider calls, merge, push, worktree deletion or production approval.
