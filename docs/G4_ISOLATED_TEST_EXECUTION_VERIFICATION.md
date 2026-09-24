# Agentic Verification Loop: G4 isolated reviewer-test execution and counts

## Objective and authority

- Requirement: roadmap G4; plan §26.2/§26.4; adversarial-loop plan Phase L2.
- Outcome: execute one immutable reviewer package against one current implementation
  binding inside the existing no-mount offline container, retain exact count evidence,
  and validate paired known-good/known-bad controls.
- Invariants and non-goals: exact input identities before and after execution; only
  declarative direct-symbol adapter materialization; no host mounts, network,
  credentials, repository mutation, VCS, provider, correction or acceptance authority.
- Risk class: high-risk execution trust boundary.
- Implementation owner: Codex under Joshua Myers's direction.
- Verifier or accountable approver: Joshua Myers; the slice does not approve a
  correction campaign or production write path.
- Starting revision: `331874d0da17e43cd5115f7d3ff65f62f1d2afbc`, clean
  worktree.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Exact isolated execution | blocking | immutable request/job/receipt identities and pre/post input replay | drift, substitution or noncanonical input fails closed |
| Count integrity | blocking | collected, started, executed, skipped, expected-failure and outcome counts plus ordered-ID digests | observations exactly satisfy the frozen collection contract |
| Known controls | blocking | paired receipt validator | known-good succeeds; known-bad has an assertion failure and no infrastructure/import error |
| Containment and cleanup | blocking | fixed Docker command, timeout/output/input bounds, no mounts/network and cleanup regressions | no fallback execution and every failure cleans up |
| Authority containment | blocking | literal receipt/request fields and CLI events | repository/VCS/network/credential/provider/correction/acceptance remain false |
| Delivery | high | focused adversarial tests, static/full gates and installed-wheel smoke | all evidence reconciled without a live call |

## Budget and stopping rules

- Maximum iterations: four evidence-changing passes.
- Elapsed-time or review window: one offline implementation session.
- Compute/cost ceiling: local tests/build and immutable-container fixtures only; no
  paid or live provider calls.
- Pass rule: all blocking rows pass and no unresolved high-severity finding remains.
- Diminishing-return rule: stop after clean hostile fixtures, source gate and packaged
  artifact replay add no new finding.
- Escalation/domain-input trigger: any need for repository-write, Git, credential,
  provider or correction authority returns to the owner and a later G4 slice.
- Rollback or abort condition: host execution fallback, executable adapter input,
  incomplete counts, mutable receipt, mounts/network or unbounded output/processes.

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Immutable request/job/observation/receipt/control contracts and worker/child boundary | Real known-good and assertion-only known-bad fixtures; count mismatch and error fixtures | G4-EX-001 high; G4-EX-002 blocking | Require an explicit disjoint lifecycle root; launch tests in a clean `-I` child with materialized paths before installed packages | Focused G4 tests passed after corrections |
| 2 | Exact pre/post input verification, generated direct-import adapter and count/ID evidence | Same-name `mos_eisley` fixture, stale-tree replay and canonical/tamper attacks | G4-EX-003 high | Require distinct implementation-tree hashes in paired controls, not only distinct record hashes | Ruff and Pyright clean; focused package/binding/execution suite 25/25 |
| 3 | CLI boundaries, private no-overwrite records and hostile resource cases | Output overflow, attempted material mutation, deadline, overlapping lifecycle and duplicate-key attacks | no new blocking finding | Retain fail-closed behavior and add a regression proving an overlapping lifecycle root cannot invoke the container | Focused 25/25; four command help surfaces parsed |
| 4 | Documentation, project-memory and installed-artifact reconciliation | Complete source suite, local fixture rerun, export/build and wheel smoke | expected sandbox-only loopback errors | Reconcile the 31 `PermissionError` cases with the same 48 tests outside the restricted sandbox; no product correction | 2,456 source tests observed; 48/48 local rerun; 1,787/1,787 wheel smoke |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| G4-EX-001 | CLI originally inherited `OfflineContainer`'s repository-relative lifecycle default | Container cleanup metadata could write beneath the implementation repository | high | Accepted finding; corrected by making `--lifecycle-root` required and disjoint from inputs, implementation and output | CLI overlap regression returns 2 before `execute` | Joshua Myers |
| G4-EX-002 | The controller process may already have imported an installed target package with the same name as bound source | Tests could execute installed code instead of exact materialized code | blocking | Accepted finding; corrected with a clean isolated `python -I` child and explicit path precedence | same-name `mos_eisley` fixture passes only against materialized implementation | Joshua Myers |
| G4-EX-003 | Paired controls originally required distinct binding hashes but not distinct tree hashes | Metadata-only binding differences could masquerade as good/bad implementation controls | high | Accepted finding; validator now requires distinct implementation-tree digests | identical-tree control construction is rejected; good/bad fixture remains valid | Joshua Myers |

## Exit

- Stop reason: all blocking rubric rows pass and the final installed-wheel gate added
  no finding.
- Rubric result and blocking findings: pass for this offline slice; all three accepted
  findings are corrected and no blocking finding remains.
- Full quality-gate command and result: `make check` passed Ruff (812 files), Pyright
  and all non-socket source behavior; its test phase ran 2,456 tests with exactly 31
  sandbox-denied loopback fixture errors and 4 skips. The affected
  `test_mcp_http`, `test_mcp_oauth` and `test_mcp_schema` modules then passed 48/48
  outside that restriction. `make verify-export build` passed, and `make smoke`
  passed 1,787 installed-wheel tests.
- Production-like replay/fault/rollback evidence: real clean-child known-good,
  assertion-only known-bad, skip/count, error, output, mutation and deadline fixtures
  pass. The product runner has only an `OfflineContainer.execute` path, while focused
  tests substitute its response rather than invoking Docker. Existing full isolation
  regressions cover fixed flags and cleanup; the built wheel contains the controller,
  CLI, worker and child modules. No production or live provider execution occurred.
- Remaining uncertainty: trusted VCS/E2 provenance, authenticated creator approval,
  bounded correction and final independent review remain later G4 gates.
- Human/domain approval: Joshua Myers directed this offline slice.
- Durable facts: promoted to `PROJECT_MEMORY.md`, `PROJECT_BRIEF.md`, the README,
  roadmap and plan. The isolated execution/count slice is complete without enabling
  the remaining gates.
