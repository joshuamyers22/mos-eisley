# Offline analytical evaluation verification — 2026-09-09

Scope: `feat/analysis-evaluation`, stacked on the evidence/artifact client.
Objective: distinguish a checked returned cell from a match to independently
reviewable question/source/SQL expectations, while preserving every planned
assignment in the report. This is an implementation verification record, not
independent domain review or an empirical quality assessment.

The passing threshold is focused adversarial tests, strict typing/lint, the full
repository quality gate and installed-wheel execution. A synthetic MCP roundtrip
and the installed data-mcp Parquet conversation provide different integration
checks. Stop after these pass; paid assessment and production deployment require
reviewed domain fixtures and their existing transfer/spending controls. No new
dependencies, paid calls, production sources or native credential stores are used.

`tests/test_analysis_evaluation.py` adds 14 tests covering:

- A correct-looking number paired with wrong SQL, metric arguments, source, units
  or expected snapshot metadata mismatches the reviewed expectation.
- Question, model, configuration/prompt/catalog identity, promoted revision and
  asserted review time are checked. Legacy bundles without identity cannot match.
- Missing, recorded failure and invalid artifacts remain in planned totals with
  unknown usage/spending. Duplicate/unexpected assignments and reused artifacts
  reject the input; suite/artifact digest changes and payload tampering fail.
- Exact scalar types, inclusive decimal tolerance, numeric strings, invalid numeric
  syntax and unordered overlapping-tolerance matching preserve multiplicity.
- Task exports omit golden labels and the unselected split. Duplicate questions,
  cross-split declared families and incomplete per-arm labels fail validation.
- Clarification matching checks status only and keeps explanation quality false.
  Source truth, snapshots, controlled comparison and promotion remain false.
- Offline CLI output is owner-private, omits source content and refuses overwrites
  with fixed diagnostics. Synthetic model transport is never called by grading.
- The packaged synthetic MCP demonstration freezes its suite before capture and
  reports one match, one recorded failure and one missing assignment. Its fixture
  and reviewer labels establish no independent authority.

The existing 42 analytical tests and the 14 new evaluator tests pass. The standalone
CLI demonstration also produces the intended 1/1/1 counts. The actual installed
data-mcp Parquet integration passes; its optional disposable PostgreSQL test is
skipped because no disposable DSN was supplied. Server implementation is unchanged.

`make check` passes Ruff lint/format, strict Pyright, 703 tests (two optional
cross-repository skips), 88% branch-inclusive coverage, locked-export verification,
package build and 89 installed-wheel tests outside the checkout. No new dependency
or runtime lock changes were needed. Local documentation links and diff checks pass.

Limits: expected SQL compares exactly and can reject equivalent formatting. Raw
query units are review assertions. Hashes and timestamps do not authenticate
execution or independent review. Missing/failure spending is unknown, and report
sums are explicitly partial in those cases. Grade while bundles remain accessible;
saved evaluation JSON has separate owner-managed retention. No ontology-free/live
experiment runner, source freeze, statistical inference or learning promotion is
implemented. See the [operator contract](ANALYSIS_EVALUATION.md).
