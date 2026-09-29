# Agentic Verification Loop: review response-envelope budget correction

## Objective and authority

- Requirement, issue, or project-brief link: G2 and qualification finding Q-004
- User journey or operational outcome: a valid bounded critic or judge JSON answer
  remains usable when its canonical response also contains bounded opaque reasoning
- Invariants and non-goals: explicitly bound the visible answer, provider-token, spending,
  wire, no-retry and evidence-integrity limits; do not alter old evidence, authorize a
  live campaign, access credentials, contact a provider or grant launch authority
- Risk class: high-risk correctness, private-data and financial boundary
- Implementation owner: Codex under Josh Myers's direction
- Verifier or accountable approver, if required: Josh Myers; automated checks and
  agent adversarial review are supporting evidence, not independent approval
- Commit/revision and starting worktree state: `fed1e5d11349cc00a629467a168a4c0175cbba1b`;
  pre-existing qualification/host changes are intentionally preserved

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Exact Q-004 correction | Blocking | Synthetic response containing valid JSON plus opaque reasoning larger than the old combined limit | Accepted below the separate 8,000-byte text and 64,000-byte canonical-envelope limits |
| Correctness and failure handling | Blocking | Exact-limit and one-byte-over tests for answer and envelope; broker completion receipts | Each independent limit fails closed and no retry is added |
| Security/privacy/data integrity | Blocking | Request hash/profile and retained-evidence tests | Both limits are content-bound; no raw secret/provider data enters tracked fixtures |
| Financial authority | Blocking | Spend/request inspection | `max_output_tokens` and pricing/reservation calculations are unchanged |
| Maintainability/operability | High | Types, names, focused tests and adversarial review | One pure budget policy owns the distinction and diagnostics identify the failed limit |

## Budget and stopping rules

- Maximum iterations: four evidence-changing implementation/review passes
- Elapsed-time or review window: current engineering session
- Compute/cost ceiling, if material: zero provider calls and USD 0 provider spend
- Pass rule: focused reproducer, affected suites, `make check` and container gate pass;
  no blocking adversarial finding remains
- Diminishing-return rule: stop after a full passing gate plus one distinct
  adversarial boundary inspection that adds no blocker
- Escalation/domain-input trigger: the fix requires changing provider payload fields,
  spending authority, old evidence interpretation or campaign policy
- Rollback or abort condition: visible JSON becomes less bounded, opaque bytes become
  unbounded, request identity omits either limit, or any test requires live access

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Planned separation of answer reserve and canonical response envelope | Final campaign produced 8,221/8,617-byte canonical responses under a 4,000-byte ceiling | Q-004 blocking | Test the initial 4,000-byte answer assumption against exact retained shapes before freezing the correction | Design only |
| 2 | Exact offline retained-shape inspection | Visible JSON was 4,243/2,680 bytes; canonical envelopes were 8,617/8,221 bytes | Initial 4,000-byte answer proposal rejected | Freeze an explicit 8,000-byte text cap and 64,000-byte envelope; leave the 4,096-token/spend ceiling unchanged | Both exact shapes parse and validate offline; no provider access |
| 3 | Independent request-bound text/envelope enforcement in reviewer, broker and launch projection | Exact/one-byte-over synthetic boundaries, opaque-reasoning positive case, old optional request/profile decoding, and broad review regressions | No blocking implementation finding in focused review | Serialize launch limits explicitly so a seal cannot inherit changed defaults silently | 422-test broad regression set passed; final gates pending |
| 4 | Full package and container integration | `make check` passed; first container pass reached the isolation smoke and found its manually constructed broker request omitted the now-required text cap | Integration fixture omission, high verification value but no product-path bypass | Add the fixture's explicit 4,000-byte text cap and rerun the whole container gate | Full check and corrected complete container gate passed |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| Q-004 | `BudgetPolicy` output reserve was assigned to `ModelRequest.max_output`, which also counted opaque reasoning | Valid responses could fail before quorum | Blocking historical defect | Accepted and corrected offline without reinterpreting the failed run | Positive opaque-reasoning case, exact answer/envelope boundaries, and retained-shape replay pass | Josh Myers |

## Exit

- Stop reason: pass rule and diminishing-return rule met after four distinct passes
- Rubric result and blocking findings: all correction dimensions pass; no open
  correction blocker remains. Historical qualification Q-004 remains immutable.
- Full quality-gate command and result: unrestricted `make check` passed Ruff,
  Pyright, 2,451 source tests with four skips and 89% coverage, export verification,
  sdist/wheel builds and 1,842 installed-wheel tests. The first sandboxed run failed
  only because localhost socket fixtures were prohibited. Corrected `make container`
  passed the image/CLI, isolation and all review smoke gates.
- Production-like replay/fault/rollback evidence, if applicable: both private retained
  response shapes validated offline under the corrected profile; synthetic exact-limit
  regressions cover acceptance and rejection; no provider replay was authorized
- Remaining uncertainty, owners, and dates: real provider response distributions may
  change; any future live campaign requires a new owner-reviewed plan and authority.
  Owner Josh Myers, review trigger before any proposed live qualification.
- Human/domain approval, if required: implementation requested by Josh Myers; this
  automated/self-review evidence is not independent human approval
- Durable facts promoted to tests, docs and `PROJECT_MEMORY.md`: independent caps,
  exact boundaries, historical immutability and no-new-live-authority rule

## Diagnostic resource accounting (optional)

- Iterations and elapsed time: four evidence-changing passes
- Aggregate tokens/cost, when policy permits: USD 0 provider spend
- Accepted versus rejected findings: Q-004 accepted and corrected in code; the
  historical qualification failure remains terminal
- Escaped defects or regressions discovered later: unknown
