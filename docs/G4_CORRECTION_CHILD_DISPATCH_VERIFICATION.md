# G4 correction-child dispatch verification

- Starting revision: `f8544c9`; working tree was clean.
- Requirement: [G4 roadmap](ROADMAP.md) and [plan §26.2](mos-eisley-plan.md#262-review-loop-contract).
- Risk class: high; local authorization, source disclosure and replay boundary.
- Objective: independently authorize and spend one exact correction-child proposal
  dispatch while preserving no-host-write and no-acceptance invariants.
- Non-goals: live provider, actual Git mutation, measured spend, final acceptance.
- Selected pinned guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`,
  `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
  `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, `templates/WORK_NOTE.md`.

## Rubric and bounded loop

| Dimension | Blocker | Evidence/threshold |
|---|---|---|
| Exact one-use task/cycle authority | High | Signed creator order, stored claim and duplicate negative |
| Child source/identity containment | High | Bound existing owned files, signed proposal, unowned/no-op negatives |
| Creator test visibility without mutation | High | Exact separately signed read-only test view and replacement-scope negative |
| Approved plan visibility | High | Plan bytes rehashed against the original creator-approved digest |
| No host mutation or acceptance | High | Git status/revision replay and false authority fields |
| Deadline and allowance | High | Cooperative async timeout and reported usage ceiling |
| Reproducibility | Material | Focused suite, strict typing, full package gates |

Maximum two implementation/review passes before escalation; no live calls or
external spend. Stop if a concrete provider/write adapter or accountable review
is required. The first pass added the separate approval, source offer, signed
proposal, one-use claim, contained validation and receipt. The second pass added
child-signature replay, task/cycle rather than approval-hash claim identity,
deadline-bound async proposal generation and retained proposal bytes. No agent
self-review is treated as independent production approval.

## Checks

| Check | Command | Result |
|---|---|---|
| Focused correction regressions | `uv run --frozen python -m unittest discover -s tests -p 'test_reviewer_correction.py' -q` | 6 passed after final source/test changes; real temporary Git and actual local worker subprocess |
| Lint/format/type | `uv run --frozen ruff check .`, `ruff format --check .`, and `pyright` | Passed on the final worktree; 0 typing errors |
| Combined gate | `make check` | **Not passed:** 2,478 source tests, 32 errors, 4 skipped; 31 MCP localhost binds denied by sandbox; one G4 worker error arose from an in-flight source edit while this long suite was already loaded. This run does not verify the final revision. |
| MCP environment reconciliation | permitted `uv run --frozen python -m unittest discover -s tests -p 'test_mcp*.py' -q` | 68 run, 4 skipped, 0 failures; reconciles the 31 localhost-bind errors |
| Locked export and build | `make verify-export build` | Passed; sdist and wheel built from final source |
| Installed-wheel smoke | `make smoke` | Sandbox attempt failed on DNS fetching a hash-pinned dependency; permitted retry passed 1,834 installed-wheel tests, 0 failures |
| Aggregate coverage diagnostic | `uv run --frozen coverage report --skip-covered` on the sandboxed source run | 87% total branch-inclusive coverage; the source suite itself did not pass, so this is not a passing full gate |
| Whitespace | `git diff --check` | Passed |

The focused test uses a real temporary Git fixture and actual local worker
subprocess. Docker's production image is **not** claimed by that subprocess fixture.

## Findings and exit

- Blocking production finding: no concrete provider/spend adapter, trusted child
  key custody, authenticated critic quorum, or write/integration broker. Deferred
  to separately approved slices; not silently treated as completed.
- The offline boundary exits with focused regressions, typing, lint, package
  build and installed-wheel smoke passing. The sandboxed aggregate source run remains
  inconclusive as a final-revision gate for the reasons above; do not describe
  it as green. Final acceptance and live dispatch remain denied.
