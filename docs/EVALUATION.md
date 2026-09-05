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

Execution and adjudication are deliberately separate in this milestone. An
executor must expose only a case's `brief` to the candidate, never
`expected_findings`, `risk_tags` or split labels. A human or deterministic fixture
then records one observation for every assignment in exactly one split. Provider
failures are observations, not rows to discard.

```sh
uv run --frozen mos eval-score \
  --dataset eval/dataset.json \
  --plan .mos-eisley/eval/plan.json \
  --observations eval/holdout-observations.json \
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
the dataset, plan and exact observation-set digests.

Errors count as missed detections and incomplete runs. If a cost gate is present,
cost must be recorded for every trial. Cost is stored as integer micro-US dollars;
subscription quota or opportunity cost is not yet comparable and must not be
invented as dollar cost.

## What this does not prove

The tool cannot prove that labels were hidden from an external executor, that a
human judgment is correct, or that thresholds were authored before results were
seen. It also does not seal a holdout set against repeated analyst access, correct
for multiple comparisons, model correlated cases, stratify by prompt profile, or
detect provider drift. These controls are required before a report can promote a
routing policy. See the milestone review for the explicit remaining risks.
