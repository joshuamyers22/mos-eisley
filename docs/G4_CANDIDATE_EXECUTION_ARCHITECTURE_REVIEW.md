# Adversarial Code and Architecture Review: G4 candidate execution

## Review metadata

- Repository: `mos-eisley-memory-selection`; branch
  `feat/production-template-guidance`; starting commit `3a121fe`.
- Reviewer: Codex, author self-review; not independent human review.
- Date: 2026-09-24.
- Product purpose: admit and dispatch one separately approved candidate test run
  after exact G4 provenance/control replay, without expanding write or provider
  authority.
- Runtime: Python 3.12, Pydantic, Ed25519, fixed-argv Git, existing immutable
  no-mount Docker runner.
- Scope: candidate admission/CLI, generic-runner guard, real-Git and worker tests;
  no model-child implementation or production deployment.
- Rubric and threshold: all authorization, one-use, source/image, isolation and
  receipt-integrity findings are blocking.
- Iteration ceiling: two evidence-changing review passes; stop on an unresolved
  high finding or accountable owner approval need.

## Executive verdict

- Offline implementation: complete; full installed-wheel suite remains non-green
  in unrelated review fixtures under aggregate load.
- Release recommendation: block production candidate use until owner review and
  the remaining G4 gates; offline slice may be retained after tests pass.
- Highest risk: same-UID controller/store or Docker/Git compromise and the lack of
  externally witnessed one-use state.
- Strongest property: the ordinary isolated-run API and CLI now reject candidate
  requests; only the separate signed approval and claim path reaches execution.

## Architecture map

- Domain policy: immutable approval, admission and dispatch contracts plus exact
  lineage/window checks in `reviewer_candidate_execution.py`.
- Application use case: replay prior evidence/current Git, consume approval once,
  invoke the existing isolated runner and replay Git after execution.
- Infrastructure: existing read-only Git recorder, immutable Docker container and
  owner-owned mode-`0700` claim store.
- Delivery: `reviewer_candidate_execution_cli.py` with check, dispatch and verify
  commands; no private-key or provider entry point.
- Dependency flow: CLI → candidate policy/use case → provenance, execution and
  isolation services. External signing remains outside CLI.

## Attack-led findings

| ID | Severity | Evidence and consequence | Correction and acceptance |
|---|---|---|---|
| G4-CE-001 | high | Generic isolated runner previously accepted `role=candidate`, bypassing new approval | Public control runner now rejects candidate before container invocation; targeted regression |
| G4-CE-002 | high | A receipt could assert a consumed claim without replaying persisted claim bytes | Receipt verification now reads the private exact claim and compares canonical admission bytes; tamper regression |
| G4-CE-003 | medium | Library callers could place state under the source repository even if CLI rejected it | Library verifies package, claim and lifecycle locations outside Git before dispatch |

## Clean-code and boundary checks

- Versioned immutable contracts, bounded canonical decoders and explicit false
  downstream-authority fields keep the policy testable without Docker.
- The CLI constructs the concrete container and keeps private-key access out of
  command options. The library accepts a concrete container for the trusted host;
  Python function privacy is not treated as a security boundary.
- No exception handler turns a failed run into success. A spent claim without a
  receipt is intentionally ambiguous and requires a new approval.
- Worker/image and same-UID trust remain explicit; passing counts are not a
  semantic proof of test quality or implementation correctness.

## Verification and follow-up

- Focused real-Git, worker, replay and CLI regressions: 41/41 source and installed
  G4 tests passed. Ruff/Pyright, export and build passed.
- Complete source gate: 2,471 tests with 31 sandbox-denied loopback errors and four
  skips; all 48 affected MCP tests passed outside that restriction.
- Complete installed-wheel smoke: non-green twice in review/launch fixtures (first
  1,787 tests, two errors; second 1,827 tests, two errors and one failure). The
  implicated launch-admission and conformance-acceptance modules passed 24/24 and
  14/14 respectively in isolation. The aggregate timing/interference cause is
  not established; do not treat the isolated pass as a full-gate pass.
- No accountable independent approval was performed by this self-review.
- Follow-up trigger: any change to approval fields, policy enrollment, claim
  persistence, Git replay, isolation flags or final-review contract.
