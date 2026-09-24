# G4 correction integration verification record

## Objective and rubric

- Requirement: [G4 integration contract](G4_CORRECTION_INTEGRATION.md),
  [plan §§11, 26.2 and 26.4](mos-eisley-plan.md).
- Risk: high; implementation is offline-only and not production authorization.
- Owner: Josh Myers. Implementation and self-review: Codex. No independent
  production approval is claimed.
- Invariants: separate exact creator grant and exclusive task/cycle claim;
  original checkout unchanged; only signed existing owned bytes in a private
  detached worktree; commit parent/path/blob/patch replay; no hook/filter,
  provider, test, merge/push or acceptance authority.
- Blocking evidence: positive fixture commit and signed replay; negative grant,
  one-use, unsafe checkout, hook and dirty-worktree cases; lint, typing, source
  tests, artifact build and smoke.
- Budget: two evidence-changing passes and one aggregate `make check`. Stop on
  source mutation, unexpected Git behavior, or need for real production authority.

## Evidence and finding disposition

| Pass | Evidence | Result |
|---|---|---|
| 1 | End-to-end signed proposal to detached commit | Passed; original HEAD/status unchanged |
| 2 | Full upstream replay, shared-repository identity, hook suppression, unsafe attributes, linked-store denial and dirty-worktree negatives | Passed; post-commit original-checkout status and direct private-store validation were tightened after the aggregate run and focused regressions passed |

No external model/provider call was made. The private worktree and local Git
objects are fixture-only in verification. Production key custody, host controls,
dependency completeness, real broker spend and independent review remain open.

## Quality gates

| Check | Result |
|---|---|
| Focused integration tests | `uv run --frozen python -m unittest discover -s tests -p test_reviewer_correction_integration.py -v`: 2 passed after the final code correction |
| Lint and typing after final correction | `ruff check .` passed; `pyright` 0 errors/warnings |
| Export and build after final correction | `make verify-export build` passed; sdist and wheel built |
| `make check`, sandboxed | Non-green: 2,480 source tests, 31 localhost-bind permission errors in MCP fixtures, 4 skipped; lint/typing passed before the test stage |
| `make check`, permitted localhost retry | Passed: source tests, 88% branch-inclusive coverage, export verification, sdist/wheel build, and installed-wheel smoke (1,834 tests passed) |
| Full gate after final status/store corrections | Not rerun; focused integration test, lint, typing, export and build were rerun and passed |
| Independent approval | Not performed; production release blocked |

## Exit

The offline boundary is implemented and locally verified. The permitted full
gate passed before the final original-checkout clean-status and private-store checks; their
focused regression and affected static/build checks passed afterward. This is
not a final correction, production release or independent acceptance.
