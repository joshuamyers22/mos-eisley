# Comparison schedule verification — 2026-09-09

Scope: `feat/analysis-comparison-schedule`, stacked on the raw analytical baseline.
Objective: freeze a complete label-free order, balance arm positions, and identify
recorded execution-order violations without dropping failed/missing assignments or
claiming authenticated execution. Passing threshold: deterministic/adversarial tests,
strict static checks, real synthetic MCP execution and the full package quality
gate. Stop after these pass; actual domain quality requires reviewed fixtures and
a separately controlled assessment. No paid calls, production data, provider API
changes, native credentials or new dependencies are used.

Nine tests in `tests/test_analysis_schedule.py` cover:

- Deterministic complete blocks and balanced positions for two, three and eight
  arms across incomplete and complete rotations; a changed seed changes order.
- Golden-label exclusion and selected-split export, with omitted/duplicated/reordered
  assignments, changed seeds/tasks, missing splits, single-arm designs and invalid
  creation timestamps rejected.
- Correct recorded order despite shuffled observation input, and distinct detection
  of runs predating the freeze, reversed starts and overlapping intervals.
- Missing, failed, invalid and no-longer-readable artifacts retain unknown timing
  and stay in planned totals. Correct returned values alone do not satisfy order.
- Owner-private CLI output, explicit independently retained schedule digest,
  no-overwrite behavior and fixed failure diagnostics.
- A packaged raw/promoted synthetic MCP comparison writes its suite/schedule before
  four runs and passes the offline assessment. Fault injection records all four
  failed attempts without exposing error payloads or dropping the denominator.

Focused validation: all nine schedule tests pass; Ruff and strict Pyright pass.
`make check` passes lint/format, strict Pyright, 720 tests (two optional
cross-repository skips), 88% branch-inclusive coverage, locked-export verification,
package build and 106 installed-wheel tests outside the checkout. The strengthened
CLI digest-pin and successful-assessment checks also pass in the focused suite and
installed-wheel run. Local documentation links, diff checks and the integrated
Downloads plan copy pass verification.

The synthetic questions share one family and the fixed fixture is asserted, not an
independently frozen source. Tests exercise scheduling/accounting, not model accuracy.
Reports keep execution authorship, source snapshots, controlled-comparison validity
and promotion readiness false. See the [operator contract](ANALYSIS_COMPARISON_SCHEDULE.md).
