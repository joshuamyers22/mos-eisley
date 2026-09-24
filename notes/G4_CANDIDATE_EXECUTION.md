# Work Note: G4 candidate execution admission and dispatch

- Status: closed for offline implementation; production verification open
- Owner: Joshua Myers; implementation by Codex
- Started (UTC): 2026-09-24T13:05:00Z
- Last updated (UTC): 2026-09-24T15:14:00Z
- Review or delete by: retain as G4 delivery evidence

## Objective and completion evidence

- Intended outcome: admit one exact signed candidate reviewer-test request only after
  replaying authenticated custody, trusted Git and known-control evidence; dispatch
  through the existing immutable-image offline container and retain a canonical
  receipt.
- Invariants: separate candidate approval from prior non-authorizing artifacts;
  no repository/VCS writes, host execution, network, credentials or provider calls;
  fail closed on stale identity, expired approval, replay, drift or failed counts.
- Non-goals: child implementation dispatch, correction, final whole-suite testing,
  independent review, production acceptance, and proof of physical key custody.
- Evidence: focused hostile tests, static checks, one combined `make check`, build
  and installed-wheel smoke where feasible; no live calls.
- Risk class: high-risk authorization and untrusted-code boundary. Resource ceiling:
  one implementation pass plus two evidence-changing review passes, no paid calls;
  stop on failed boundary, resource ceiling, or need for accountable approval.

## Context retrieved

- `AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, plan §§14.2.1,
  15.7 and 26.2, and the four preceding G4 contracts.
- Selected guides/templates: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`,
  `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
  `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md` and
  `templates/WORK_NOTE.md`.

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-24 13:05 | decision | Prior provenance and controls explicitly deny candidate authority; require a distinct exact approval and dispatch gate | G4 contracts | Implement bounded admission |
| 2026-09-24 13:30 | evidence | Exact approval, current Git, one-use claim, generic-runner denial and CLI regressions pass | focused G4 tests | Run full source and wheel gates |
| 2026-09-24 14:00 | evidence | Source gate ran 2,471 tests with 31 sandbox-denied localhost errors; all 48 affected MCP tests passed with loopback permission | `make check`; targeted MCP rerun | Build and smoke wheel |
| 2026-09-24 15:14 | evidence | Export/build and installed-wheel G4 tests pass; two complete wheel-smoke attempts remain non-green in review fixtures, while implicated modules pass in isolation | verification record | Retain limitation and request accountable review before production use |

## Handoff

- Current state: offline candidate admission/dispatch implementation complete in
  the containing revision; starting worktree was clean at commit `3a121fe`.
- Next smallest safe action: diagnose aggregate installed-wheel review-fixture
  timing/interference, then obtain accountable owner review before production use.
- Blocker and required authority/input: full installed-wheel smoke remains
  non-green; physical key custody and production approval require Joshua Myers.
- Checks already run: 41/41 focused and installed G4 tests; Ruff/Pyright;
  2,471-test source gate reconciled with 48/48 unrestricted localhost tests;
  export/build; two full wheel-smoke attempts; 24/24 launch and 14/14 conformance
  installed-wheel modules in isolation.

## Close and promote

- Outcome and verification: exact signed admission and one-use isolated candidate
  dispatch implemented; complete installed-wheel smoke is unresolved, not green.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.g4.candidate-execution`.
- Decision promoted to documentation: `docs/G4_CANDIDATE_EXECUTION.md`.
- Regression test: `tests/test_reviewer_candidate_execution.py`.
- Temporary artifacts: smoke script removed its ephemeral environments; a small
  diagnostic wheel environment remains under `/private/tmp/mos-g4-wheel-diag.4DK7Fd`.
