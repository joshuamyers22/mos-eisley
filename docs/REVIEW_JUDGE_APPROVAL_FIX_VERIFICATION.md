# Agentic Verification Loop: formal judge approval and allowance cleanup

## Objective and authority

- Requirement: correct the short formal judge-approval window and the unresolved unused allowance exposed by the latest G2 campaign.
- User journey or operational outcome: a human can inspect and authorize the formal judge phase inside a separately bounded window while the remaining execution budget is preserved.
- Invariants and non-goals: standard review timing and canonical bytes remain unchanged; no provider, exchange, pricing, retry, credential, campaign-quorum or live-authority rule changes; transferred or uncertain request exposure is never released.
- Risk class: material authorization and financial-accounting boundary.
- Implementation owner: Joshua Myers.
- Verifier or accountable approver: Joshua Myers before any new production campaign.
- Commit/revision and starting worktree state: clean `bac51fe`; correction initially uncommitted.

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Formal approval viability | blocking | Deterministic paused-clock controller test | 600-second hash-bound grace preserves remaining active execution time |
| Correctness and failure handling | blocking | Controller, flow, campaign and launch suites | Terminal paths are one-use, bounded and fail closed |
| Security/privacy/data integrity | blocking | Contract substitution and ledger fault tests | No configurable grace; no critic/destination/uncertain release; no new secret or live access |
| Maintainability/operability | material | Named constant, schema validation, inspection and operator docs | One explicit rule with backward-compatible standard artifacts |

## Budget and stopping rules

- Maximum iterations: four evidence-changing passes.
- Elapsed-time or review window: one offline implementation session.
- Compute/cost ceiling, if material: local synthetic tests only; zero provider calls.
- Pass rule: red regressions, focused affected suites, static checks, then one `make check`.
- Diminishing-return rule: stop after the full gate and diff/contract audit reveal no blocking finding.
- Escalation/domain-input trigger: any need to lengthen provider/runtime limits, release ambiguous exposure, repair historical ledger state, or make live calls.
- Rollback or abort condition: standard canonical changes, weaker accounting, or unrelated dirty-file overlap.

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Reproduction tests | Formal clock advance and graceful cancel ledger snapshot | J-001 blocking: approval consumes active time; J-002 high: unused allowance remains held | Keep regressions red before source changes | One error and one assertion failure |
| 2 | Schema-2 timing and exact retirement | Standard/formal contracts, transfer lineage and inspection inventory | No new blocker; schema substitution needed explicit rejection | Fix grace at 600 seconds and require formal preparation scope | Targeted regressions pass |
| 3 | Compatibility sweep | Approval, campaign, launch, conformance, runtime-evidence and terminal language | Historical conservative-spend assertions needed narrow updates | Preserve critic/uncertain holds; update only unused-source expectations | 211 affected review tests passed |
| 4 | Repository gate and audit | The first full source run reached 2,422 tests | J-005 material: ledger-wide entry equality rejected valid shared-ledger observations before their acceptance-layer exposure check; 31 MCP cases could not bind loopback in the sandbox | Record whether cleanup itself changed the source, use that terminal marker for transfer attribution, rerun 86 affected tests, then run the complete gate with loopback access | 86 focused tests pass; final `make check` passes 2,422 source and 1,779 wheel tests |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| J-001 | Formal controller deadline and terminal campaign evidence | Human judge authorization can expire after successful critics | blocking | Accepted; separate bounded approval grace from active execution budget | Paused-clock formal controller regression | Joshua Myers |
| J-002 | Deferred allowance after graceful terminal cancellation | Known-unused capacity remains reported as charged exposure | high | Accepted; retire only exact still-held non-dispatch source | Exact/idempotent ledger and controller-terminal regressions | Joshua Myers |
| J-003 | Schema-2 construction boundary | A free-form grace could weaken bounded authorization | high | Rejected by construction; require exactly 600 seconds and matching formal scope | Contract substitution tests and model validation | Joshua Myers |
| J-004 | Transfer/record crash boundary | A missing transfer record can hide the destination identity | high | Conservatively retained; inspector reports incomplete attribution and never releases or guesses | Inspection missing-record coverage | Joshua Myers |
| J-005 | First full-gate acceptance cases | Ledger-wide entry equality made unrelated shared-ledger entries look like missing transfer targets | material | Accepted and corrected: only the atomic cleanup transaction can set the terminal marker; acceptance retains its separate unexplained-exposure check | Shared-ledger acceptance, zero-retirement and missing-transfer tests | Joshua Myers |

## Exit

- Stop reason: passed.
- Rubric result and blocking findings: every blocking threshold passed; J-001 through J-005 are corrected and no blocking finding remains in the offline slice.
- Full quality-gate command and result: unrestricted `make check` passed Ruff lint/format, Pyright, all 2,422 source tests with 4 skips and 89% coverage, export verification, sdist/wheel build, and all 1,779 installed-wheel tests in 991.070 seconds.
- Production-like replay/fault/rollback evidence, if applicable: synthetic fault and cancellation paths only; no live replay.
- Remaining uncertainty, owners, and dates: exact corrected commit/image and a fresh formal campaign remain open; Joshua Myers, 2026-09-22.
- Human/domain approval, if required: required before any new live call.
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: timing, cleanup, inspection and incident behavior are captured in regression tests and controller/approval/conformance/spending/inspection documentation; `delivery.next.live-review` records the next safe boundary.

## Diagnostic resource accounting (optional)

- Iterations and elapsed time: four-pass ceiling; one offline session.
- Aggregate tokens/cost, when policy permits: no provider cost.
- Accepted versus rejected findings: five accepted and corrected findings; no deferred product finding.
- Escaped defects or regressions discovered later: none recorded at close time.
