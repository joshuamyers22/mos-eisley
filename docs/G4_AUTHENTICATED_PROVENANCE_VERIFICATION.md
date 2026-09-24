# Agentic Verification Loop: G4 authenticated custody and VCS/E2 provenance

## Objective and authority

- Requirement: roadmap G4; plan §§11, 14.2.1, 15.7 and 26.2.
- Outcome: authenticate the exact creator approval, blind reviewer-package custody,
  bounded child assignment/result, trusted read-only Git reconstruction and prior
  known-control evidence in one immutable non-authorizing record.
- Invariants and non-goals: signatures bind exact canonical bytes; the Git broker
  executes fixed read-only argv with a minimal environment; final source and child
  lineage are reconstructed from Git objects; no child dispatch, repository/VCS
  write, credential, network, provider, correction or acceptance authority.
- Risk class: high-risk provenance and authority boundary.
- Implementation owner: Codex under Joshua Myers's direction.
- Verifier/accountable approver: Joshua Myers; physical key custody and independent
  human identity remain external facts.
- Starting revision: `2f02080d62b4b0b1e26d264a52adba47c248151f`, clean worktree.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Authenticated custody | blocking | domain-separated Ed25519 artifacts and enrolled policy | exact package/reference/role chain verifies; substitutions fail |
| Trusted VCS reconstruction | blocking | fixed read-only Git broker and object/tree replay | final binding and current clean tree equal the claimed commit |
| E2 lineage | blocking | creator assignment, distinct child result and ancestry/diff checks | bounded meaningful child commit is an ancestor and changes only owned paths |
| Authority containment | blocking | literal false fields and CLI events | no artifact grants execution, write, VCS mutation, provider, correction or acceptance |
| Delivery | high | hostile regressions, static/full gates, export/build and wheel smoke | all evidence reconciles without live/provider calls |

## Budget and stopping rules

- Maximum iterations: four evidence-changing passes.
- Time/compute ceiling: one offline implementation session and local Git fixtures.
- Pass rule: all blocking rows pass with no unresolved high-severity finding.
- Stop/escalation: any need for a real private key, model child, repository mutation
  outside disposable fixtures, provider call or production approval returns to owner.

## Iterations

| # | Implemented slice | New evidence/context | Findings | Decision | Gates |
|---:|---|---|---|---|---|
| 1 | Domain-separated policy and creator/reviewer/child/VCS artifacts; custody and final-record replay | Separated and ADR-0005 single-operator fixtures; signature, role, canonical-JSON and package-reference substitution attacks | G4-AP-001 high | A signed child assignment asserted test protection but did not carry an exact creator-test path inventory | Focused signature/custody tests passed after correction |
| 2 | Fixed-argv read-only Git broker and exact object/tree/diff reconstruction | Disposable real Git repositories with dirty, untracked, wrong-path, wrong-HEAD and malicious `core.fsmonitor` cases | G4-AP-002 high | Recheck exact `HEAD` after mutable binding/worktree reconstruction, not only before it | Ruff/Pyright clean; eight provenance tests passed |
| 3 | CLI record/sign/assemble/replay boundary and durable contract | Full CLI path, private no-overwrite records, external signing and current Git replay | no new blocking finding | Keep all private keys outside production CLI and every downstream authority false | Four combined G4 modules passed 33 tests; process/isolation discovery passed 7 |
| 4 | Project-memory, roadmap, source/build and installed-artifact reconciliation | Complete source suite, unrestricted loopback rerun, export/build and installed wheel | expected restricted-sandbox socket errors only | Reconcile all 31 localhost errors with the same 48 tests outside the restriction | 2,464 source tests observed; 48/48 rerun; 1,787/1,787 wheel smoke |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Disposition and correction | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| G4-AP-001 | Initial `G4ChildAssignment` carried owned paths but no complete creator-test path inventory | A child could be described as test-blind without a cryptographically bound disjoint scope | high | Accepted; assignment now carries sorted nonempty `creator_test_paths`, asserts completeness and rejects overlap; Git replay requires every actual changed path to be within owned paths | overlap construction and out-of-owned result regressions fail | Joshua Myers |
| G4-AP-002 | Git reconstruction originally verified exact `HEAD` only before reading trees/blobs/worktree state | A concurrent revision change could make one record combine observations from different heads | high | Accepted; exact `HEAD` is checked again after all mutable binding/worktree reads; later lookups use exact immutable object IDs | malicious config/wrong-head fixture fails; clean replay passes | Joshua Myers |

## Exit

- Stop reason: all blocking rubric rows pass and the installed-wheel gate added no
  finding.
- Rubric result: pass for this offline slice; both high findings are corrected and
  no blocking finding remains.
- Full gates: `make check` passed Ruff (820 files) and Pyright, then ran 2,464 tests
  with exactly 31 sandbox-denied loopback errors and four skips. The affected
  `test_mcp_http`, `test_mcp_oauth` and `test_mcp_schema` modules passed 48/48 with
  loopback permission. `make verify-export build` passed; the wheel contains both
  provenance modules; `make smoke` passed 1,787 installed-wheel tests.
- Remaining uncertainty: signatures prove enrolled-key control and byte integrity,
  not physical identity, honest judgment, external timestamps or independence.
  Creator-test inventory completeness and meaningful-subtask semantics remain signed
  accountable claims. Git/OS/same-UID state and dependency/image correspondence
  remain trusted. Candidate dispatch, correction and final review remain later G4
  gates.
