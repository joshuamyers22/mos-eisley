# Agentic Verification Loop: G3 fixed-matrix feasibility preflight

## Objective and authority

- Requirement, issue, or project-brief link: roadmap G3; plan §§18.3, 26.3–26.5
- User journey or operational outcome: an owner can reject an unaffordable or
  statistically unattainable fixed-matrix study before constructing packets or spending
- Invariants and non-goals: preserve the implemented equal-group, fixed-matrix,
  Hoeffding/Bonferroni method and hard caps; budget clean and defective evidence,
  repetitions and every route; do not design adaptive inference, inspect holdout,
  call a provider, authorize execution, or claim utility/savings
- Risk class: material correctness and financial planning
- Implementation owner: Codex under Josh Myers's direction
- Verifier or accountable approver, if required: Josh Myers; an independent
  statistical reviewer is still required before consequential empirical claims
- Commit/revision and starting worktree state: `681da9f2fbfc51ef231fa60630a23d2439010cc0`;
  pre-existing G2 edits in `provider_broker.py` and its test are preserved untouched

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Plan-reference reproduction | Blocking | Four strata, six routes, three repetitions and 0.05 best-case radius | 1,732 groups; 13,856 clean cases; 249,408 clean assignments |
| Correctness and failure handling | Blocking | Unit/property-boundary tests | Full family correction, integer ceiling and cap comparisons are exact; perfect/zero-risk targets are finite-sample impossible |
| Financial/data integrity | Blocking | Route-cost coverage and digest tests | Every exact candidate has one nonnegative ceiling; spend includes every minimum assignment; mismatches fail closed |
| Authority separation | Blocking | Contract and CLI inspection | Report explicitly denies execution, promotion and routing activation; no credentials/network/provider path |
| Maintainability/operability | High | Ruff, Pyright, focused tests and CLI round trip | Pure typed module, private deterministic output and actionable issue codes |

## Budget and stopping rules

- Maximum iterations: four evidence-changing passes
- Elapsed-time or review window: current engineering session
- Compute/cost ceiling, if material: no provider calls and USD 0 provider spend
- Pass rule: reference, feasible, cap-infeasible, exact-threshold and malformed-input
  tests pass with focused lint/type checks; affected regression tests pass
- Diminishing-return rule: stop after the pass rule plus a distinct diff/requirement review
- Escalation/domain-input trigger: implementation would change the estimator,
  confidence allocation, hard caps, holdout policy or provider/spend authority
- Rollback or abort condition: repetitions increase independent sample size, costs or
  routes are omitted, an infeasible study reports feasible, or the report grants authority

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Requirements and template survey | Existing scorer lacks the plan-required executable pre-spend calculation | One bounded G3 gap; no G2 collision | Add a pure feasibility report over current contracts | Design complete |
| 2 | Pure fixed-matrix calculation and offline CLI | Reference example, feasible design, spend rejection, exact targets and artifact round trip | No calculation defect in focused checks | Preserve the same family formula and explicit non-authority fields | Ruff, Pyright and 15 evaluation tests pass |
| 3 | Distinct accounting/integrity review | Per-route values lacked cost-basis identity; assignment-only spend could omit grading/preparation | G3-F-002 high | Bind each cost basis and require non-assignment spend before calling the result total | Ruff, Pyright and 16 evaluation tests pass; affected coverage 89% |
| 4 | Repository gate and packaging replay | Full Pyright exposed the monolithic CLI dispatcher's complexity ceiling; the initial sandboxed suite could not bind localhost for MCP tests | G3-F-003 high; environment limitation | Move the command into the existing specialized evaluation dispatcher, then rerun the full gate unrestricted | `make check`: 2,488 tests pass, 4 skipped, 89% coverage; export and build pass; 1,855 installed-wheel smoke tests pass |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| G3-F-001 | Plan §26.3 requires a pre-spend calculation; current statistics module only scores observed groups | An impossible matrix can be planned conceptually before `make_plan` rejects only its assignment count | Blocking for first G3 slice | Accepted; implement a no-send preflight without changing inference | Reference calculation and cap/spend negative tests | Josh Myers |
| G3-F-002 | First-pass `RouteCostCeiling` contained only an operator-authored integer and total cost counted assignments only | Price/request provenance or grading/preparation spend could be silently omitted | High | Accepted; bind a reviewed cost basis per route and require an explicit non-assignment cost ceiling | Strict schema, cost arithmetic and documentation inspection | Josh Myers |
| G3-F-003 | Full Pyright reported a complexity ceiling in the already-large top-level CLI dispatcher | Type analysis of the modified CLI became incomplete and emitted secondary false positives | High | Accepted; route `eval-feasibility` through the existing specialized evaluation dispatcher | Full Pyright reports zero errors | Josh Myers |

## Exit

- Stop reason: implementation and bounded verification are complete; the broader G3
  study remains deliberately open
- Rubric result and blocking findings: pass for the offline preflight; no open blocking
  implementation finding. The plan-reference design reports 1,732 groups per
  profile/split, 27,712 total clean-plus-defective cases and 498,816 assignments,
  so it fails the existing case and assignment ceilings before spend.
- Full quality-gate command and result: `make check` passed Ruff, formatting, Pyright,
  2,488 source tests with 4 skipped and 89% coverage, export verification, and package
  build; the installed wheel then passed 1,855 smoke tests
- Production-like replay/fault/rollback evidence, if applicable: not applicable; offline calculation
- Remaining uncertainty, owners, and dates: actual route price bases, representative
  independently graded labels, sealed baseline/ablation policy, held-out-session
  custody and independent statistical review remain open; G2 completion is required
  before live quality or savings claims
- Human/domain approval, if required: pending Josh Myers and independent statistical review
- Durable facts promoted to tests, docs, and `PROJECT_MEMORY.md`: feasibility contract,
  CLI behavior, plan-reference lower bound and non-authority boundary
