# Work Note: G4 bounded correction-cycle evidence gate

- Status: offline implementation complete; production verification open
- Owner: Joshua Myers; implementation by Codex
- Started (UTC): 2026-09-24T15:33:00Z
- Last updated (UTC): 2026-09-24T18:44:00Z
- Review or delete by: retain as G4 delivery evidence

## Objective and completion evidence

- Intended outcome: prevent an unadjudicated failed candidate test from silently
  authorizing a repair; bound any recorded correction to two exact cycles, a fixed
  task allowance/deadline, renewed custody/Git and a fresh candidate receipt.
- Invariants: no child/provider dispatch or write, no test weakening, no automatic
  acceptance; non-code, flaky and infrastructure findings stay distinct.
- Evidence: real-Git/worker fixtures, signed-role and cycle replay negatives,
  source and installed-wheel checks; no live calls.

## Context retrieved

`AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, roadmap G4,
plan §§14.2.1 and 26.2, loop-plan L2/L3, and the five prior G4 contracts.
Selected template guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
`templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, and `templates/WORK_NOTE.md`.

## Observations and attempts

| Time (UTC) | Type | Observation/action | Evidence | Next step |
|---|---|---|---|---|
| 15:33 | decision | Candidate counts alone cannot identify a correction finding | prior G4 receipt schema | add bounded worker failure IDs |
| 17:45 | evidence | One and two-cycle real-Git fixtures, signature/replay and renewed-chain checks pass | `tests/test_reviewer_correction.py` | add CLI and broad gates |
| 17:50 | decision | Preserve actual dispatch and acceptance denials; aggregate allowances are conservative, not measured spend | G4 contract and threat model | obtain accountable review before production |
| 18:44 | evidence | Clean locked installed wheel passed 1,832 tests; source sandbox loopback denials reconciled with 68-test permitted MCP pattern | `make smoke`; verification record | close offline slice, retain production gates |

## Handoff

- Current state: offline correction evidence/claim/completion boundary implemented
  in this revision; no production child dispatch enabled.
- Next smallest safe action: separately design and review contained correction
  child dispatch, then final whole-suite and independent implementation review.
- Blocker and required authority/input: actual signer custody, critic quorum,
  production correction execution and final independent review need separate
  approval and implementation.
- Checks already run: focused correction tests, Ruff and Pyright; final combined
  gate results belong in the verification record. Source suite ran 2,476 tests
  with 31 sandbox loopback denials; the unrestricted MCP pattern passed 68 tests
  with four skips. Export/build and 1,832-test installed-wheel smoke passed.

## Close and promote

- Outcome and verification: offline correction evidence gate and CLI complete;
  focused checks and clean installed-wheel smoke pass. Production dispatch and
  acceptance remain denied.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.g4.bounded-correction`.
- Decision promoted to: `docs/G4_BOUNDED_CORRECTION.md`.
- Regression test: `tests/test_reviewer_correction.py`.
- Temporary artifacts: test temporary directories are removed automatically.
