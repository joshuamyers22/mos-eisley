# Offline analytical evaluation

The evaluator compares private analytical artifacts with separately reviewed
expectations. A returned number can match its captured cell and still answer the
wrong question: this layer also checks the question, run identity, promoted
revision, metric or query arguments, SQL, source metadata, units and expected cells.
It makes no provider calls, reruns no SQL, and performs no ontology promotion.

## Try the synthetic workflow

Create an owner-only directory and run the packaged demonstration:

```sh
mkdir -m 700 /absolute/private/analysis-evaluation
uv run --frozen mos analysis-eval-demo \
  --result-root /absolute/private/analysis-evaluation
```

The printed UUID directory contains `suite.json`, a label-free `tasks.json`, one
private captured result bundle, `inputs.json` and `report.json`. The suite is written
before a scripted agent calls a real synthetic MCP server. Its three assignments
intentionally produce one match, one recorded timeout and one missing run. This
checks the workflow; it measures no model accuracy. The demo's fixture digest labels
synthetic input and is not independent proof of source contents.

## Freeze a reviewed suite

The demonstration supplies the complete JSON shape. The authoritative closed
schemas are `EvaluationSuite` and `EvaluationInputs` in
`src/mos_eisley/analysis/evaluation.py`. A suite contains:

- An ID, reviewer label and timezone-aware review timestamp.
- Up to eight arms, each with provider/model, semantic revision and run identity.
- Up to 128 unique cases with ID, question family, development/holdout split,
  question, asserted fixture digest and exactly one expectation per arm.
- Expected status (`answer`, `clarify`, `unavailable`); answers additionally contain
  one to 32 expected cells and an ordered/unordered claim comparison rule.

Each expected cell pins the tool, exact arguments, exact submitted SQL, required
source metadata, reviewed units, zero-based row, column, JSON scalar value and an
optional absolute tolerance string. Metric expectations require the metric name
and revision plus backend, source and units. Raw query expectations require their
source/root argument; their units are a review assertion because query responses
may not report units. Add snapshot/path/grain/timezone metadata where the source
actually supplies it. Missing required metadata is a mismatch.

New analytical results record SHA-256 hashes of the resolved analysis configuration
(excluding the question), system prompt and exposed canonical tool catalog.
Review these before assessment using `run_identity(config, definitions)` with the
same `analysis_mcp_config(mcp, config.context_mode)` and discovered definitions as
the intended run. Provider,
model, semantic revision and question are also checked separately. Changing budgets,
retention settings or selected tool definitions changes the identity. Existing
schema-2 bundles without this optional identity still verify/export, but cannot
match an evaluation arm. These hashes do not pin dependency versions, remote model
revisions, server code, endpoints or database snapshots.

Keep golden suites outside every runtime-served directory. Export only the selected
split's questions, fixture labels and arm identities for execution:

```sh
uv run --frozen mos analysis-eval-plan \
  --suite /absolute/private/suite.json --split development \
  --output /absolute/private/tasks.json
```

The task file includes the canonical suite digest and excludes expected statuses,
values, SQL and units. Case IDs and questions must be unique; a declared family
cannot span development and holdout. These checks cannot recognize paraphrased
leakage or prove independent review. Reviewer identity, timestamps and fixture
hashes are operator assertions, not signatures or preregistration evidence.

## Grade every planned assignment

Run each question through the existing analytical command with explicit private
retention and its usual source, transfer and spending controls. This milestone
provides no batch/live experiment runner. Record an observation for each case/arm
using the absolute bundle directory and its manifest's `payload_sha256`, or a
failure category (`timeout`, `provider_error`, `tool_error`, `validation_error`,
`cancelled`). Pin the `suite_sha256` from the exported plan and select its split.
An omitted observation becomes a missing run. Never replace a failure with a
successful retry under the same assignment.

```sh
uv run --frozen mos analysis-evaluate \
  --suite /absolute/private/suite.json \
  --inputs /absolute/private/inputs.json \
  --output /absolute/private/report.json
```

All planned case/arm pairs appear in the report. Duplicate or unexpected pairs and
reusing one artifact digest across assignments reject the submission. Missing,
failed, expired, invalid and mismatching artifacts remain in the planned totals.
Runs that predate the asserted review time mismatch. Existing artifact ownership,
mode, size, expiry, hash and internal evidence validation all apply.

Cell matching preserves JSON types: integer `42`, floating `42.0`, string `"42"`
and boolean values differ. Default tolerance `"0"` uses exact values. An explicit
nonzero decimal tolerance permits a numeric difference within that inclusive bound,
while preserving the scalar type. Numeric strings use JSON number syntax; NaN,
infinity and unsupported numeric ranges fail. SQL and arguments compare exactly;
equivalent SQL with different formatting can conservatively mismatch. Required
source metadata is a subset match. Unordered matching reorders claims while
preserving multiplicity and each claim's row/column; it does not reorder table rows.
Clarification/unavailable cases match status only, without judging their prose.

Reports contain IDs, hashes, outcome/reason codes and descriptive per-arm counts,
reported usage categories, retained spending and summed measured latency. They omit
questions, SQL, source values and local artifact paths. Unknown usage, spending and
latency have explicit counts; reported sums are partial when those counts are
nonzero. Retained spending is local ledger accounting, not reconciled invoices.
Fixture runs contribute zero monetary cost. Incoherent usage is invalid.
`observations_complete` means no assignments are missing; it does not mean they
passed. Exit status is 0 for all matches, 1 for a completed report containing any
other outcome, and 2 for invalid input or output failure. The intentional demo
returns 0 when its workflow completes.

Output parents must already be private owner-only directories. Files are written
mode 0600 exclusively, without overwriting existing files. Suite/input parsing and
output are bounded to 2 MB. Demo result bundles expire after 24 hours; grading must
occur while evidence is accessible. Evaluation JSON files have no automatic expiry
or cleanup: retain/delete them under the owner's policy. Source bundle expiry does
not erase a saved report or its supporting golden labels.

## Limits and next experiment

Every report explicitly leaves source truth, fixture snapshots, controlled
comparison, explanation quality and promotion readiness unverified. Owner-editable
artifacts and digests establish internal consistency, not execution authorship.
Correct expected values and reviewed SQL remain a domain responsibility.

The next experimental work is to prepare reviewed domain fixtures and disjoint
question families, then run a separately budgeted assessment with fixed settings,
frozen sources and recorded failures. An explicit
[raw-data baseline](ANALYSIS_RAW_BASELINE.md) now runs the same controller without
promoted context. Raw arms require `context_mode: "raw"`, a null semantic revision
and raw query expectations. Promoted arms keep the default mode and their revision.
[Frozen schedules and recorded-order assessment](ANALYSIS_COMPARISON_SCHEDULE.md)
now provide reproducible case blocks with balanced arm positions. Automatic live
execution, probe/maintenance accounting and statistical inference remain unimplemented.
This offline grader supports part of Ana Lite Stages 0 and 6; it does not complete
the controlled comparison or justify adding automatic learning.
