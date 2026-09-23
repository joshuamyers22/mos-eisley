# Agentic Verification Loop: sealed cleanup admission and conservative no-ops

## Objective and authority

- Requirement: correct the two findings upheld by the formal campaign at source
  commit `98869cccbecad01fe419ec9ad79f7d4ebce55d23`.
- User journey: a stopped formal review retires its unused judge allowance only when
  the controller is bound to an exact independently sealed campaign slot; cleanup
  never releases transferred or uncertain exposure.
- Invariants and non-goals: preserve schema-1 behavior, formal judge timing, one-use
  dispatch, exact ledger identity, critic and destination exposure, and historical
  campaign evidence. Do not make provider calls, authorize retry, or activate live
  review.
- Risk class: high-risk authorization and financial-accounting correction.
- Implementation owner and accountable approver: Joshua Myers.
- Starting state: clean `feat/production-template-guidance` worktree at `98869cc`.
- Selected production-template guides: `templates/AGENTIC_VERIFICATION_LOOP.md`
  and `templates/THREAT_MODEL.md`.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Sealed cleanup authority | blocking | Direct-controller and bound-campaign regressions | Unbound formal cleanup preserves the hold; exact sealed binding permits one retirement |
| Transfer and uncertainty integrity | blocking | Controller and ledger state comparisons | Transferred/uncertain source or destination exposure is unchanged by cleanup |
| Idempotence and isolation | blocking | Repeated cleanup with critic, destination and unrelated entries | First eligible cleanup changes only the source; later calls change nothing |
| Compatibility | high | Controller, campaign, inspection and launch suites | Standard behavior and formal timing remain unchanged |
| Repository quality | high | Focused tests, static checks and full `make check` | All applicable gates pass, or an environmental limitation is reported exactly |

## Budget and stopping rules

- Maximum evidence-changing iterations: four.
- Provider-cost ceiling: zero; all verification is offline and synthetic.
- Pass rule: every blocking row passes, the affected test suites pass, and the full
  repository gate has no product failure.
- Diminishing-return rule: stop after two clean, meaningfully different verification
  passes add no finding.
- Escalation trigger: a required campaign binding would create recursive commitment,
  weaken signature/ledger checks, or require changing historical evidence.
- Abort condition: any test shows released uncertain/provider-request exposure or
  live credential/provider access.

## Iterations

| # | Implemented slice | New evidence/context | Findings | Decision and correction | Gates |
|---:|---|---|---|---|---|
| 1 | Red regressions before runtime changes | Direct formal construction retired its unsealed hold; cleanup against an exact uncertain entry raised instead of preserving exposure | Both upheld findings reproduced | Require an independently sealed slot for controller cleanup and make an exact non-held entry an idempotent no-op | Expected red failures observed |
| 2 | Sealed campaign binding and conservative ledger retirement | Bound decline, unbound cancellation, post-transfer cleanup, uncertain receipt, repeat cleanup and unrelated-entry isolation | No blocking finding remained in the affected paths | Retain the immutable campaign selection in the controller, reread and compare the exact seal/slot/preview/ledger/policy at terminal time, and preserve every exact non-held state | 148 focused and compatibility tests passed; Ruff and Pyright passed |
| 3 | Repository-wide and built-artifact verification | Full source discovery, socket-capable MCP retry, export verification, sdist/wheel build and isolated installed-wheel smoke | Source discovery's only 31 errors were `PermissionError` from the managed sandbox denying loopback binds; the same MCP family passed outside that restriction | Classify the 31 errors as environmental, not product failures; retain the exact commands and results below | 2,429 source tests exercised; 68 MCP tests passed with 4 expected skips; 1,785 wheel tests passed |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Disposition | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| CSF-001 | `BrokeredReviewController._terminal` | Unsealed formal controller can release capacity | blocking | Accepted; bind cleanup to validated sealed slot evidence | Direct unbound and sealed-bound tests | Joshua Myers |
| CSF-002 | `SpendLedger.retire_unused` and controller cleanup | Transferred/uncertain state can raise or lack preservation evidence | blocking | Accepted; exact non-held states become no-op and receive state-isolation regressions | Transfer, uncertainty and repeat tests | Joshua Myers |

## Exit

- Stop reason: all blocking rubric rows passed and a second, independently packaged
  verification pass added no finding.
- Rubric result and blocking findings: pass; CSF-001 and CSF-002 are corrected with
  executable regression evidence.
- Verification results:
  - `uv run --frozen ruff check .`, `ruff format --check .`, and `pyright`: pass.
  - Four affected-suite groups: 148 tests passed.
  - `coverage run -m unittest discover -s tests`: 2,429 tests exercised, 4 skipped;
    its 31 errors were exclusively sandbox-denied loopback binds in MCP HTTP/OAuth
    fixtures. `unittest discover -s tests -p 'test_mcp*.py'` outside that restriction:
    68 passed, 4 skipped. No product test failed.
  - Coverage report: 88% total.
  - Export verification and sdist/wheel build: pass.
  - Installed-wheel smoke: 1,785 tests passed.
- Remaining uncertainty: no provider call or live campaign was made. The correction
  still requires a new exact commit, production image, and fresh authorization
  artifacts before any later live qualification campaign.
- Durable facts promoted: focused regressions, controller/campaign/spending docs,
  threat model, changelog and the existing `delivery.next.live-review` memory key.
