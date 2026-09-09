# Frozen analytical comparison schedules

A reviewed suite defines what to ask and how to grade it. A comparison schedule
also freezes the order of every case/arm assignment before execution. The offline
assessment checks recorded run timing against that order while preserving the
existing correctness, missing/failure, usage and spending results.

## Try the synthetic workflow

```sh
mkdir -m 700 /absolute/private/comparison
uv run --frozen mos analysis-comparison-demo \
  --result-root /absolute/private/comparison
```

The command creates a private UUID directory containing `suite.json`,
`schedule.json`, `inputs.json`, `assessment.json` and captured result bundles. It
freezes two synthetic questions and the raw/promoted arms, writes the suite and
schedule before generation, and follows the schedule through real local MCP
sessions with scripted model responses. Each arm runs first once. The four saved
answers and recorded order should match; no paid provider or production source is
used. Both questions belong to one synthetic family, so these are not four
independent observations of model quality. The fixture digest is an asserted
synthetic label, not proof of source contents.

Unexpected completed demo attempts are recorded as `validation_error` failures
and remain in the report; there are no retries. Cancellation or process death can
leave an incomplete demo directory. This demonstration is not a durable live
experiment executor and has no resume/recovery protocol.

## Freeze an operator-reviewed schedule

Prepare an [evaluation suite](ANALYSIS_EVALUATION.md) with two to eight arms and at
least one case in the selected development/holdout split. For a raw/promoted
comparison, follow the [baseline configuration guide](ANALYSIS_RAW_BASELINE.md).
Choose and retain one 64-character lowercase hexadecimal seed before examining
outcomes. A fresh value can be generated locally with
`python3 -c 'import secrets; print(secrets.token_hex(32))'`.

```sh
uv run --frozen mos analysis-eval-schedule \
  --suite /absolute/private/reviewed-suite.json \
  --split development --seed YOUR_64_HEX_SEED \
  --output /absolute/private/schedule.json
```

Retain the printed canonical `schedule_sha256` independently before running any
assignments.
The schedule contains the frozen suite digest, selected split's questions, fixture
labels, arm identities, creation timestamp, seed and numbered assignments. Golden
statuses, SQL, units and expected cells are omitted. The unselected split's
questions are not exported. Keep the reviewed golden suite outside runtime-served
source directories.

The versioned algorithm `sha256_case_blocks_rotating_arms_v1` hashes the seed with
case identities to select case order and with arm identities to select the initial
arm order. Each case forms one block containing every arm. Rotating the arm order
by one position for each successive case balances every arm's position counts to
within one, even for an incomplete rotation. The ordering is reproducible and all
assignments are explicit; reordered, omitted or duplicated assignments fail
validation. The current limits are 128 cases, eight arms and 1,024 assignments,
with a 2 MB schedule/input/output limit.

This balances positions; it does not balance every possible carryover effect or
establish independence among related questions. A seed is not evidence of random
selection if an operator tries multiple seeds after seeing outcomes. Do not choose
a new schedule to replace an unfavorable result. Preserve the original failures
and record any later experiment as a separate reviewed assessment.

## Execute and record

The schedule/assessment commands are offline and dispatch neither MCP nor provider
calls. Execute each numbered assignment through the existing `analysis-run` path,
using its exact question, arm configuration, source fixture, transfer/spending
controls and explicit private retention. Complete or record a failure for one
assignment before starting the next. The schedule does not reserve money, enforce
execution order, start a batch, retry a failed run or prove source isolation.

Build the usual `EvaluationInputs` file pinned to the suite digest and split, with
one captured artifact path/hash or failure per attempted case/arm. Omitted entries
remain missing. Input-list order is irrelevant: the assessor maps observations to
the frozen assignments and checks the timestamps inside the pinned artifacts.

```sh
uv run --frozen mos analysis-eval-assess \
  --suite /absolute/private/reviewed-suite.json \
  --schedule /absolute/private/schedule.json \
  --schedule-sha256 THE_INDEPENDENTLY_RETAINED_DIGEST \
  --inputs /absolute/private/inputs.json \
  --output /absolute/private/assessment.json
```

Assessment first revalidates the complete schedule against the reviewed suite,
selected split and seed, then performs the existing source/SQL/cell evaluation.
It reloads the pinned valid bundles for timing checks; an artifact that expires or
changes between reads has unknown timing. It reports these per-assignment reasons:

- `run_predates_schedule`: recorded start precedes schedule creation.
- `out_of_order`: recorded start precedes an earlier scheduled run's start.
- `overlap`: the run starts before an earlier scheduled run finishes.
- `timing_unavailable`: the run is missing, failed, invalid or cannot be reloaded.

Known runs are still compared across gaps, but any gap keeps
`recorded_order_matches` false. Failure observations currently have no timing or
usage receipt, so those quantities stay unknown. The nested evaluation retains
every planned assignment and its correctness/usage/spending outcome. An answer can
match its expected cells while failing order checks; matching order can coexist
with incorrect answers. The CLI returns 0 only when all answers match and all
recorded timings satisfy the schedule, 1 for a completed unsuccessful assessment,
and 2 for invalid inputs or output failure.

Reports contain IDs, hashes, timestamps, reason codes and evaluation aggregates;
they omit question text, SQL, source values and artifact paths. Parent directories
must already be owner-private. Output files use mode 0600 and refuse overwrite.
Assessment must occur before source bundle access expiry. Schedule, input and
assessment JSON have separate owner-managed retention with no automatic cleanup.

## What the result establishes

`recorded_order_matches` means the supplied controller timestamps satisfy the
frozen sequential ordering and do not predate the recorded schedule. Use a
consistent clock across runs; clock corrections/skew can cause mismatches. These
are editable local records and digests, not an authenticated observation of actual
execution, independent preregistration, provider authorship or a source freeze.

Execution authorship, source snapshots, controlled-comparison verification and
promotion readiness remain explicitly false. Domain review, stable fixtures,
provider-version controls, collection of failure costs/timing, maintenance/probe
accounting, a durable live executor and appropriate statistical assessment remain
open. Matching these synthetic fixtures just verifies the workflow.
