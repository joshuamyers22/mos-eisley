# Offline evaluation foundation

Mos Eisley's automatic model and reasoning selection remains disabled. This
milestone creates reproducible evidence artifacts; it does not infer a routing
policy and it makes no provider calls.

The design follows OpenAI's guidance to define the objective, collect a
task-specific dataset, define metrics, run comparisons and continue evaluating.
The same guidance recommends realistic distributions, explicit held-out criteria
and human calibration rather than generic or vibe-based scores. OpenAI also advises
increasing reasoning effort only when evaluations show a measurable quality gain.

References:

- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)

## Artifact flow

`eval-plan` reads four operator-authored inputs: a labeled dataset containing both
calibration and holdout cases, a candidate grid, pre-registered quality gates and a
randomization seed. It expands the full case × route × repetition matrix in a
deterministic shuffled order and writes a mode-0600, content-addressed plan.

```sh
uv run --frozen mos eval-plan \
  --dataset eval/dataset.json \
  --candidates eval/candidates.json \
  --gate eval/gate.json \
  --repetitions 10 --seed 20260905 \
  --output .mos-eisley/eval/plan.json
```

Each candidate is the concrete backend × provider × model × effort tuple plus its
client version and registry digest. API and subscription clients therefore remain
different candidates even when they expose the same model name.

Create an execution batch and a separate private mapping. A fresh 256-bit nonce
produces opaque HMAC sample IDs. The batch contains only each brief and concrete
route; it contains no case IDs, expected findings, risk tags or split labels. Never
give the mapping or labeled dataset to an execution backend.

```sh
uv run --frozen mos eval-blind \
  --dataset eval/dataset.json \
  --plan .mos-eisley/eval/plan.json \
  --split holdout \
  --batch-output .mos-eisley/eval/holdout-batch.json \
  --mapping-output .mos-eisley/eval/holdout-map.json
```

The only implemented executor is request-bound and recorded. It reads the blinded
batch and a cassette, verifies exact request coverage, and produces raw results
without case identities or labels. It makes no provider calls.

```sh
uv run --frozen mos eval-run-recorded \
  --batch .mos-eisley/eval/holdout-batch.json \
  --cassette eval/holdout-cassette.json \
  --output .mos-eisley/eval/holdout-raw.json
```

Next, create the adjudicator packet. This joins references to completed outputs but
removes route, model, backend, case ID, split and private assignment mapping. Give
only this packet and the grading rubric to a human adjudicator. A candidate can
still identify itself in its prose, so output-level identity leakage remains a
known limitation.

```sh
uv run --frozen mos eval-grade-packet \
  --dataset eval/dataset.json \
  --plan .mos-eisley/eval/plan.json \
  --batch .mos-eisley/eval/holdout-batch.json \
  --mapping .mos-eisley/eval/holdout-map.json \
  --raw-results .mos-eisley/eval/holdout-raw.json \
  --output .mos-eisley/eval/holdout-grading.json
```

The adjudication JSON binds the grading packet digest, an adjudicator ID, method,
rubric digest, UTC completion time and one judgment for every completed sample.
Each judgment must cover every emitted finding by zero-based index and content
hash, with a rationale and a disposition. Detections and false-positive counts are
derived from those decisions, rather than supplied separately by the grader.
Failed executions require no content judgment. Compile those judgments only in the
trusted controller, which verifies the full dataset → plan → batch/map → raw result
→ grading packet → adjudication chain. Export, grading and scoring each recheck the
complete case × route × repetition matrix. Compilation rejects missing, extra,
changed, unknown-label or unresolved finding decisions. Empty critiques require an
empty finding-decision list.

```sh
uv run --frozen mos eval-compile \
  --dataset eval/dataset.json \
  --plan .mos-eisley/eval/plan.json \
  --batch .mos-eisley/eval/holdout-batch.json \
  --mapping .mos-eisley/eval/holdout-map.json \
  --raw-results .mos-eisley/eval/holdout-raw.json \
  --grading-batch .mos-eisley/eval/holdout-grading.json \
  --adjudication eval/holdout-adjudication.json \
  --output .mos-eisley/eval/holdout-observations.json
```

An adjudication file has this top-level shape; all unknown fields are rejected:

```json
{
  "schema_version": 2,
  "grading_batch_sha256": "<64 lowercase hex characters>",
  "adjudicator": {
    "adjudicator_id": "reviewer-01",
    "method": "human",
    "rubric_sha256": "<64 lowercase hex characters>",
    "completed_at": "2026-09-05T12:00:00Z"
  },
  "judgments": [
    {
      "sample_id": "<sample ID from the grading packet>",
      "findings": [
        {
          "finding_index": 0,
          "finding_sha256": "<hash of the emitted finding>",
          "disposition": "matched",
          "expected_finding_ids": ["expected-finding-id"],
          "rationale": "This finding identifies the labeled boundary defect."
        }
      ]
    }
  ]
}
```

The supported dispositions are:

- `matched`: requires one or more known expected-defect IDs. Detection counts use
  their union, so repeated matches do not increase recall.
- `false_positive`: contributes one false positive and carries no expected IDs.
- `duplicate`: references an earlier `matched` finding with `duplicate_of`.
  Chains, cycles and references to false positives are rejected. A repeated false
  positive must still be graded as a false positive.
- `unresolved`: records uncertainty or a potentially real defect missing from the
  dataset. It blocks observation compilation until reviewed. Amending the dataset
  creates a new artifact chain; it must not silently relabel an existing holdout.

Use the SHA-256 of the canonical emitted `Finding` JSON (the Python
`Finding.finding_id` property). The enclosing grading-packet hash binds its position,
brief and expected labels as well.

## Independent grading comparison

Give the same route-blind packet and rubric to two graders separately. Keep their
results private from one another until both finish. The controller can compare
their complete artifacts without loading the dataset, routes or private mapping:

```sh
uv run --frozen mos eval-agreement \
  --grading-batch .mos-eisley/eval/holdout-grading.json \
  --left eval/grader-a.json --right eval/grader-b.json \
  --output .mos-eisley/eval/holdout-agreement.json
```

The report binds both adjudication digests and the rubric. It counts exact agreement
on disposition, expected-ID set and duplicate target; wording differences in the
rationale do not change the label comparison. Conflicts retain both decisions and
their rationales. Unresolved decisions count as unresolved conflicts even if both
graders abstain. No emitted findings produces a null agreement rate.

This is a descriptive report, with no confidence interval or quality threshold.
Distinct grader IDs alone do not authenticate people or prove independent work.
The command rejects matching IDs, mismatched rubrics and mixed human/fixture
methods, but it cannot detect collusion or shared bias. It does not pick a winning
grader. It remains useful for fixture diagnostics, but it is not the authenticated
gate.

For human grading, authenticate both exact adjudications and use
[`eval-resolve-adjudications`](DUAL_GRADE_RESOLUTION.md). That command reverifies
two distinct enrolled grader keys, preserves both signed originals and requires a
separately enrolled resolver key to sign exactly one valid decision for every
recomputed conflict. It prohibits unnecessary resolution when labels agree. The
result remains `promotion_eligible: false` and is deliberately not accepted by
`eval-compile` or `eval-score`. Single-grader compilation is still available only
for offline rehearsal while the reviewed lineage-to-observation compiler remains
unimplemented.

Adjudication schema 2 replaces the old aggregate fields. Regrade older artifacts;
there is no reliable automatic conversion from counts to per-finding decisions.

```sh
uv run --frozen mos eval-score \
  --dataset eval/dataset.json \
  --plan .mos-eisley/eval/plan.json \
  --observations .mos-eisley/eval/holdout-observations.json \
  --split holdout \
  --output .mos-eisley/eval/holdout-report.json
```

Scoring rejects a changed dataset or plan, duplicate rows, unknown ground-truth
IDs, incomplete matrix coverage and observations from the wrong split. For every
candidate it reports:

- pooled defect detection, completion and observed clean false positives with
  Wilson intervals as diagnostics only;
- group-mean Hoeffding bounds with a Bonferroni correction across all planned
  routes, three metrics and both splits;
- group counts, insufficient-evidence reasons and an explicit promotion status;
- mean observed cost, cost coverage and nearest-rank p95 latency;
- each individual gate result and overall eligibility.

The report repeats the candidate routes and gate for inspection and binds itself to
the dataset, plan, raw results, adjudication and exact observation-set digests.

Errors count as missed detections and incomplete runs. If a cost gate is present,
cost must be recorded for every trial. Cost is stored as integer micro-US dollars;
subscription quota or opportunity cost is not yet comparable and must not be
invented as dollar cost.

Eligibility now requires declared independent case groups, enough groups for each
metric, and passing the simultaneous group confidence bounds. Repetitions never
increase the independent sample count. Failed clean reviews contribute worst-case
risk in the group gate. See [statistical design](STATISTICAL_DESIGN.md) for the
estimand, formulas, assumptions, sample-size example and schema-2 migration.
Every report returns `promotion_ready: false`.

## What this does not prove

The CLI opens only the explicitly named files, and the recorded execution command
does not accept a dataset or mapping. This is a structural boundary, not process or
filesystem isolation: a future in-process live adapter could read unrelated files
unless it runs inside the planned sandbox. The tool also cannot prove that a human
judgment is correct, that thresholds were authored before results were seen, or
that the person holding an enrolled signing key is independent. Signed receipts
bind claimed identity and timestamps but do not attest physical identity or time.
It does not seal a holdout
set against repeated analyst access, verify independence of the declared groups,
correct for comparisons across separately authored plans, stratify by prompt
profile, or detect provider drift. These controls remain
required before a report can promote a routing policy.

Observation sets and reports now require raw-result and adjudication digests.
Recompile older offline observations through the artifact chain; do not insert
placeholder hashes to make an old file validate. A digest records content integrity,
not an authenticated execution. An Ed25519 adjudication receipt authenticates key
possession and exact content only under its independently supplied trust policy.
