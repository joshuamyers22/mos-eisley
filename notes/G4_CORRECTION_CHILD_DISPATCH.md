# Work Note: G4 contained correction-child proposal dispatch

- Status: offline boundary complete; production activation open
- Owner: Joshua Myers; implementation by Codex
- Started (UTC): 2026-09-24T19:08:00Z
- Last updated (UTC): 2026-09-24T20:03:00Z
- Review or delete by: retain as G4 delivery evidence

## Objective and completion evidence

- Intended outcome: one separately creator-authorized, task/cycle-unique
  correction-child proposal dispatch with exact source scope and no host write.
- Required invariants: claimed admission is evidence only; different creator/child
  signatures; frozen source/package/image; private one-use claim; no provider,
  credentials, network, Git mutation or acceptance authority.
- Evidence: real-Git and worker-subprocess fixtures, negative scope/signature/
  duplicate/allowance cases, strict typing and installed-wheel checks.

## Context retrieved

`AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, roadmap G4,
plan §§14.2.1, 15.7 and 26.2, prior G4 contracts and relevant implementation/tests.
Selected pinned guides are recorded in
`docs/G4_CORRECTION_CHILD_DISPATCH_VERIFICATION.md`.

## Observations and attempts

| Time (UTC) | Type | Observation/action | Evidence | Next step |
|---|---|---|---|---|
| 19:08 | decision | Existing correction admission expressly denies child dispatch | correction contract | add separate signed grant |
| 19:08 | decision | Existing no-mount container cannot write the host Git tree | isolation code | return proposal evidence only |
| 19:08 | evidence | Focused suite passed with real Git and worker subprocess | correction tests | run full gates |
| 19:39 | finding | Initial source-only offer omitted approved plan and concrete creator tests | plan §14.2.1 | add plan and signed read-only test view before claim |
| 19:59 | evidence | Sandboxed full source gate had 31 localhost-bind errors plus one stale in-flight G4 worker mismatch; fresh focused suite and permitted 68-test MCP rerun passed | verification record | await clean installed-wheel smoke |
| 20:03 | evidence | Fresh locked installed wheel passed 1,834 tests; source coverage diagnostic 87% with aggregate source run still non-green | verification record | close offline boundary, retain production gates |

## Handoff

- Current state: offline dispatch boundary implemented and clean-wheel verified;
  production model/write integration and final acceptance still denied.
- Next smallest safe action: review and implement concrete measured-spend coding
  broker and isolated integration/write boundary, then final whole-suite review.
- Blocker/authority: production provider use, real key custody and Git mutation
  need separate accountable authorization and verification.
- Checks already run: focused correction suite, Ruff, Pyright, build, clean-wheel
  smoke and MCP reconciliation; the sandboxed aggregate source run was non-green.

## Close and promote

- Outcome: offline one-use proposal dispatch boundary and retained receipt, with
  no production child/provider or host Git-write authority.
- Durable fact: `PROJECT_MEMORY.md` key `delivery.g4.correction-child-dispatch`.
- Decision: `docs/G4_CORRECTION_CHILD_DISPATCH.md` and threat model.
- Regression: `tests/test_reviewer_correction.py`.
- Temporary artifacts: test fixtures remove their own directories; build output
  and diagnostic log remain outside Git.
