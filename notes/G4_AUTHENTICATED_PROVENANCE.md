# Work Note: G4 authenticated custody and VCS/E2 provenance

- Status: closed
- Owner: Joshua Myers; implementation by Codex
- Started (UTC): 2026-09-24T10:40:00Z
- Last updated (UTC): 2026-09-24T13:00:00Z
- Review/delete by: retain as G4 delivery evidence

## Objective and completion evidence

- Authenticate creator/reviewer custody and bounded child lineage, reconstruct exact
  binding bytes from trusted read-only Git, and retain a canonical non-authorizing
  record.
- Completion requires hostile signature/Git fixtures, static/full gates, build and
  installed-wheel verification without live calls or production writes.

## Context retrieved

- `AGENTS.md`; Python, verification, threat and architecture guides/templates
- plan §§11, 14.2.1, 15.7, 23.1D and 26.2; ADR-0005
- G4 package, binding and isolated execution/count contracts
- existing Ed25519 policy patterns and bounded process infrastructure

## Observations

| Time (UTC) | Type | Observation | Next step |
|---|---|---|---|
| 2026-09-24 10:40 | decision | Separate creator approval, reviewer custody, child assignment/result and Git attestation domains; allow schema-2 shared human operator but require a distinct child key | Implement contracts and disposable Git fixtures |
| 2026-09-24 11:10 | finding | Initial child scope did not bind an exact creator-test inventory | Add signed complete test paths, disjoint owned paths and actual-diff enforcement |
| 2026-09-24 11:25 | finding | Initial Git reconstruction checked exact `HEAD` only before reading evidence | Recheck exact `HEAD` after all object and worktree reads |
| 2026-09-24 11:45 | evidence | Eight real-Git provenance tests, combined G4 tests and process/isolation tests pass; Ruff/Pyright clean | Run full source/build/wheel gates |
| 2026-09-24 12:40 | evidence | Source gate observed 2,464 tests with 31 restricted-loopback errors; the same 48 affected tests pass unrestricted | Build and smoke the installed wheel |
| 2026-09-24 12:53 | evidence | Export/build pass, provenance modules are in the wheel and 1,787 installed tests pass | Close records and hand off uncommitted slice |

## Handoff

- Current state: authenticated custody and trusted VCS/E2 provenance slice complete
  in the containing commit; prior isolated-execution slice is commit `2f02080`.
- Next smallest safe action: define candidate execution admission and dispatch offline.
- Blocker: none for offline completion. Candidate/correction/final-review work remains
  separately gated.
- Checks already run: focused Ruff/Pyright; 33 combined G4 tests; seven isolation
  tests; reconciled 2,464-test source gate; 48 local-socket tests; export/build; 1,787
  installed-wheel tests.

## Close and promote

- Outcome and verification: canonical authenticated chain and read-only Git replay
  implemented; two high review findings corrected; all gates reconciled.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.g4.authenticated-provenance`.
- Decision promoted to documentation: `docs/G4_AUTHENTICATED_PROVENANCE.md` and
  roadmap/plan updates.
- Regression test: `tests/test_reviewer_provenance.py`.
- Temporary artifacts removed: smoke runner removed its disposable wheel environment;
  build products remain ignored project outputs.
