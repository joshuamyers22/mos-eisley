# Work Note: G4 allowlisted implementation binding

- Status: closed
- Owner: Joshua Myers; implementation by Codex
- Started (UTC): 2026-09-24T03:08:00Z
- Last updated (UTC): 2026-09-24T04:11:14Z
- Review or delete by: retain as G4 delivery evidence
- Related issue/incident/ADR: roadmap G4; Phase L2

## Objective and completion evidence

- Intended outcome: immutable record binding the frozen reviewer package to exact
  implementation/dependency identities through a non-executable allowlist.
- Required invariants: no package mutation; complete source-root bytes; exact direct
  symbols; no execution or downstream authority.
- Evidence that will show completion: focused hostile tests, static checks, full
  source suite, export/build and installed-wheel smoke.

## Context retrieved

- `docs/adversarial-review-loop-project-plan.md` Phase L2
- `docs/G4_REVIEWER_TEST_PACKAGE.md` and its threat/verification records
- `docs/mos-eisley-plan.md` §26.2/§26.4 and `docs/ROADMAP.md`
- production verification, work-note, threat-model and Python engineering guides

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-24 03:08 | decision | Preserve the freezer as a separate commit and keep binding inert | commit `8ca3e3d` | Design declarative adapter |
| 2026-09-24 03:14 | attempt | Added exact tree declarations, fixed synthetic adapter module, direct-symbol allowlist, package double-read and canonical record | implementation and focused tests | Threat-model source inventory |
| 2026-09-24 03:18 | finding | Python-only discovery omitted runtime resources | G4-BD-001 | Inventory every source-root regular file |
| 2026-09-24 03:22 | verification | Resource-complete bounded inventory and all hostile focused cases pass; 17 package/binding tests green | focused suite, Ruff and Pyright | Run full repository gates |
| 2026-09-24 04:11 | verification | Full source run accounted for 2,448 tests; its 31 restricted-sandbox errors were all localhost fixture binds and the full affected 48-test set passed with localhost access | `make check`; `python -m unittest test_mcp_http test_mcp_oauth test_mcp_schema` | Verify export/build and wheel |
| 2026-09-24 04:11 | verification | Runtime export and sdist/wheel build passed; installed wheel passed 1,787 tests | `make verify-export build`; `make smoke` | Close slice |

## Handoff

- Current state: immutable binding record, declarative adapter and offline
  verification are complete.
- Next smallest safe action: implement an isolated runner that materializes only the
  bound direct-symbol surface and records exact collection/execution/skip counts,
  then exercise known-good and known-bad packages.
- Blocker and required authority/input: none for offline verification.
- Checks already run: focused 17-test suite; Ruff, formatting and Pyright; 2,448
  source tests accounted for; all 48 localhost MCP tests passed; export/build passed;
  1,787 installed-wheel tests passed.

## Close and promote

- Outcome and verification: complete; all in-scope blocking rows pass with the
  sandbox-only localhost split explicitly reconciled.
- Durable fact promoted to `PROJECT_MEMORY.md`: immutable package/tree/dependency
  binding through a non-executable direct-symbol adapter, with all later authorities
  false.
- Decision promoted to ADR/documentation: declarative direct-symbol adapter; no ADR
  required unless a future runner widens the surface.
- Regression test: `tests/test_reviewer_implementation_binding.py`.
- Temporary artifacts removed: temporary-directory fixtures self-clean.
