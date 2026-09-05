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
Failed executions require no content judgment. Compile those judgments only in the
trusted controller, which verifies the full dataset → plan → batch/map → raw result
→ grading packet → adjudication chain. Export, grading and scoring each recheck the
complete case × route × repetition matrix. Compilation rejects detection claims for
empty critiques and false-positive counts larger than the emitted finding count.

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
  "schema_version": 1,
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
      "detected_finding_ids": ["expected-finding-id"],
      "false_positive_count": 0
    }
  ]
}
```

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

- defect detection and completion with 95% Wilson intervals;
- the proportion of clean runs containing one or more false positives, also with
  a 95% Wilson interval;
- mean observed cost, cost coverage and nearest-rank p95 latency;
- each individual gate result and overall eligibility.

The report repeats the candidate routes and gate for inspection and binds itself to
the dataset, plan, raw results, adjudication and exact observation-set digests.

Errors count as missed detections and incomplete runs. If a cost gate is present,
cost must be recorded for every trial. Cost is stored as integer micro-US dollars;
subscription quota or opportunity cost is not yet comparable and must not be
invented as dollar cost.

## What this does not prove

The CLI opens only the explicitly named files, and the recorded execution command
does not accept a dataset or mapping. This is a structural boundary, not process or
filesystem isolation: a future in-process live adapter could read unrelated files
unless it runs inside the planned sandbox. The tool also cannot prove that a human
judgment is correct, that thresholds were authored before results were seen, or
that adjudicator identity and timestamps are authentic. It does not seal a holdout
set against repeated analyst access, correct for multiple comparisons or correlated
cases, stratify by prompt profile, or detect provider drift. These controls remain
required before a report can promote a routing policy.

Observation sets and reports now require raw-result and adjudication digests.
Recompile older offline observations through the artifact chain; do not insert
placeholder hashes to make an old file validate. A digest records content integrity,
not an authenticated execution or adjudicator identity.
