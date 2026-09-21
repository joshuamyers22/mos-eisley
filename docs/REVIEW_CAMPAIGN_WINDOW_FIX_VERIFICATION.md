# Agentic Verification Loop: review campaign preparation window

## Objective and authority

- Requirement: extend the pre-dispatch window enough for the manually gated formal three-slot production-qualification trial.
- Operational outcome: all three fixed slots can receive their complete per-slot controller window without weakening live-operation controls.
- Invariants and non-goals: increase only prepared authorization freshness from 10 to 30 minutes; do not change provider, exchange, controller, guardian, phase-authority, spending, retention, retry, or qualification rules.
- Risk class: material authorization-boundary change.
- Implementation owner: Joshua Myers.
- Verifier/accountable approver: Joshua Myers before any subsequent live campaign.
- Commit/revision and starting worktree state: `bac7dd24dc5a8a5e20b4b79a229dffc73882c88c`; unrelated G3 and documentation changes already present and excluded from this slice.

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Manual three-slot viability | blocking | Deterministic prepared-authorization expiry test | Exact 30-minute freshness window |
| Runtime-boundary preservation | blocking | Provider/controller/watchdog focused suites | All existing 60/120/300/305/360-second assertions pass unchanged |
| Authorization and spending integrity | blocking | Broker admission, campaign, replay, and ledger tests | Exact approval, one-use issue, pricing clipping, no retry, and conservative spend remain |
| Documentation and maintainability | material | Named constant and admission documentation | One source of truth; no configurable unbounded input |

## Budget and stopping rules

- Maximum iterations: three evidence-changing passes.
- Elapsed-time or review window: one implementation session.
- Compute/cost ceiling: offline local tests only; no provider calls.
- Pass rule: regression test fails before implementation, focused suites pass after implementation, then every `make check` constituent passes; localhost-dependent tests may run separately with loopback access when the default sandbox forbids socket binding.
- Diminishing-return rule: stop after the full gate and one source/diff audit produce no blocking finding.
- Escalation/domain-input trigger: any need to extend runtime or phase-authority limits, alter spending, add retries, or exceed 30 minutes.
- Rollback or abort condition: any provider/runtime cap changes or unrelated dirty-file overlap.

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Regression boundary | Exact 30-minute and pricing-clipped expectations | W-001 reproduced: old result was ten minutes | Proceed with the bounded freshness-only correction | Focused file: 23 pass, new regression fails |
| 2 | Named bounded constant and documentation | Broker admission, spending envelope, controller, campaign, runner, provider broker and guardian suites | No blocking findings; only pre-dispatch freshness changed | Retain the non-configurable 1,800-second cap and pricing clipping | 107 focused tests passed |
| 3 | Combined repository validation | Full lint/type/source/exported-wheel tests plus constant and diff audit | No product failures; the default sandbox blocked 31 localhost fixture binds, and all affected cases passed with loopback access | Accept the bounded correction; require a fresh commit/image/campaign before live evidence | Ruff and Pyright pass; 2,498 source tests accounted for with 4 skips; 68 affected MCP tests pass with 4 skips; export/build pass; 1,856 wheel tests pass; 88% coverage |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| W-001 | `PreparedReviewCall` hardcoded ten-minute expiry | Third fixed slot can inherit too little controller time after manual gates | blocking | Corrected with a bounded 30-minute freshness cap | Deterministic cap/pricing test, focused runtime suites and constant audit pass | Joshua Myers |

## Exit

- Stop reason: iteration cap reached with every rubric dimension passing and no open blocking finding.
- Rubric result and blocking findings: pass; W-001 is corrected, and no new blocking finding remains.
- Full quality-gate command and result: `make check` constituents pass. The default sandbox run discovered 2,498 source tests and passed 2,463 with 4 skips; its only 31 errors were denied loopback binds. The complete affected MCP set then passed 68 tests with 4 skips outside that socket sandbox. Ruff, format, Pyright, coverage (88%), export verification, sdist/wheel build and 1,856 installed-wheel smoke tests pass.
- Production-like replay/fault/rollback evidence: prior live timeout is the reproducer; no new live call is authorized.
- Remaining uncertainty, owners, and dates: another wholly fresh campaign is required to demonstrate the operational outcome; Joshua Myers; after commit/image rebuild.
- Human/domain approval: required before another live campaign.
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: exact 30-minute/pricing-clipped behavior is in a regression test; freshness/runtime separation is in broker and campaign documentation; `PROJECT_MEMORY.md` was deliberately left untouched.
