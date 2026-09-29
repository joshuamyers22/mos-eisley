# Agentic Verification Loop: live judge-approval finding reassessment

## Objective and authority

- Requirement: separate confirmed defects from correlated-model misconceptions in the accepted three-slot campaign and correct the confirmed defects offline.
- Operational outcome: standard reviews remain byte/behavior compatible while formal reviews retain their bounded approval grace and exact unused-allowance cleanup.
- Invariants and non-goals: no new provider, deadline, retry, credential, pricing, quorum, or launch authority; no release of transferred/uncertain exposure; no attempt to make the same model withdraw unsupported findings.
- Risk class: material authorization and financial-accounting boundary.
- Implementation owner: Joshua Myers.
- Verifier or accountable approver: Joshua Myers before any later live campaign.
- Commit/revision and starting worktree state: clean `2ed7f11b19cc7cf470c722207a40219f87f88b97`.

## Rubric

| Dimension | Blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Scope compatibility | blocking | Standard/formal controller and canonical terminal regressions | Standard never retires the deferred allowance or emits the formal cleanup marker; formal graceful exit does both |
| Transfer/accounting correctness | blocking | Transfer, terminal and ledger idempotence regressions | Successful/uncertain judge destinations remain charged and exact settled-zero source cleanup is a no-op |
| Inspection attribution | blocking | Tampered standard-marker and exact formal-source inspection tests | Cleanup completeness requires an exact formal controller/source lineage |
| Timing contract | blocking | Deterministic active-budget, grace and envelope-clipping tests | Fixed 600-second formal pause, 360-second active budget, and envelope hard clip remain unchanged |
| Repository integrity | material | Focused suites and `make check` | All selected and full gates pass without live access |

## Budget and stopping rules

- Maximum iterations: four evidence-changing passes.
- Elapsed-time or review window: one offline implementation session.
- Compute/cost ceiling: local tests only; zero provider cost.
- Pass rule: red confirmed-defect regressions, focused green suites, adversarial diff audit, then one `make check`.
- Diminishing-return rule: stop after full gate plus contract audit add no material finding.
- Escalation/domain-input trigger: any need to change the approved 600/360/1,800-second contract, repair historical ledgers, or make a live call.
- Rollback or abort condition: weaker transferred/uncertain accounting, standard canonical drift beyond restoration, or unrelated dirty-file overlap.

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Finding reassessment and red regressions | Three live terminals plus source/history/requirement trace | Two confirmed boundary gaps; three repeated claim clusters unsupported | Standard-path regressions reproduced schema drift; tampered standard cleanup marker was accepted | Red failures observed in controller and inspection suites |
| 2 | Formal-only cleanup and inspection scope correction | Exact schema/envelope/controller/ledger lineage plus transfer semantics | No new defect; broad unrelated-ledger claim narrowed to the missing formal-scope check | Gate controller retirement on schema 2; reject cleanup markers unless both start schema and preparation scope are formal; restore standard expectations | Controller: 23 passed; inspection plus launch admission: 47 passed in 114.215s |
| 3 | Repository-wide verification and adversarial audit | Source and installed-wheel behavior under the production guide set | No blocking or material regression | Keep the bounded timing contract and post-transfer behavior unchanged; document claim disposition | `make check` passed, including 2,425 source tests and 1,782 wheel tests |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| R-001 | `_terminal` retires for schema 1 and writes schema 2 when changed | Standard behavior/canonical drift | blocking | Accept; directly contradicts the documented formal-only compatibility invariant | Standard decline/cancel/failure preserve held allowance and schema-1 terminal | Joshua Myers |
| R-002 | Inspector accepts a cleanup marker without checking formal start schema | Standard evidence can claim formal cleanup | high | Accept narrowly; exact controller/source bindings already exist, but formal scope is missing | Standard schema-2 cleanup marker is rejected; formal cleanup is complete | Joshua Myers |
| R-003 | Reviewers claim terminal cleanup fails after judge transfer | Alleged missing terminal evidence | blocking if true | Reject; transfer makes the exact source settled at zero, retirement returns false, and all three live judge paths finished | Explicit post-transfer no-op and finished-terminal regression | Joshua Myers |
| R-004 | Reviewers claim the added 600 seconds violates the hard wall | Alleged deadline expansion | blocking if true | Reject; the approved contract separates fixed human grace from active execution and clips both to the formal envelope | Existing paused-clock and clipping regressions remain green | Joshua Myers |
| R-005 | Reviewers claim inspection accepts unrelated settled entries | Alleged false completeness | high if true | Reject broadly; allowance identity comes from the exact hash-bound envelope and ledger policy. R-002 covers the real missing scope check | Unrelated/shared-ledger and missing-transfer tests remain green | Joshua Myers |

## Exit

- Stop reason: pass rule met after confirmed defects were corrected, focused regressions passed, the full gate passed, and the diff/contract audit found no further material issue.
- Rubric result and blocking findings: passed offline; R-001 and R-002 are corrected. R-003 through R-005 are rejected as correlated misunderstandings, with executable counterevidence retained in tests.
- Full quality-gate command and result: `make check` passed with Ruff, Ruff formatting, Pyright, 2,425 source tests in 1,586.741 seconds (4 skipped), 89% aggregate coverage, export verification, source/wheel build, wheel smoke, and 1,782 installed-wheel tests in 973.778 seconds. The first sandboxed source run had 31 fixture setup errors solely because loopback socket binding was denied; the authorized offline rerun exercised those fixtures and passed.
- Production-like replay/fault/rollback evidence: retained live campaign used only for diagnosis; no replay dispatch.
- Remaining uncertainty, owners, and dates: correlated same-provider judgment remains a campaign limitation; Joshua Myers owns a fresh independent qualification after a clean commit and exact image rebuild. Historical retained evidence is diagnostic and is not rewritten.
- Human/domain approval: required before any new live call.
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: standard/formal controller and inspection regressions, this verification record and threat model, `CHANGELOG.md`, `docs/ROADMAP.md`, and `PROJECT_MEMORY.md`.
