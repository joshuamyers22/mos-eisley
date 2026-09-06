# Paired persona-skill evaluation

Persona skills are prompt assets, not trusted upgrades. Mos Eisley can compare one
exact persona-skill prompt with one baseline prompt while holding backend, provider,
model, reasoning effort, client version, and registry identity constant. The
workflow produces evidence only: every artifact has literal
`promotion_ready: false` or `activation_authorized: false`.

## Experimental contract

Evaluation candidates now include the complete prompt sent as reviewer instructions.
An inline baseline has this shape:

```json
{
  "schema_version": 1,
  "mode": "inline",
  "instructions": "Review the supplied change."
}
```

The candidate arm uses `mode: "skill"`, the exact activated Markdown body, and a
`SkillIdentity` containing its source-qualified whole-package digest and activated
instruction digest. Construction rejects a body that differs from that identity.
The prompt digest covers both instructions and identity. Only a `persona` skill can
become a prompt asset; procedures remain inert reference material.

The comparison plan must contain exactly two routes. They must differ only in their
prompt asset, their prompt digests must differ, and the candidate arm must identify
an exact persona package. Both calibration and holdout need declared defect, clean,
and overall independence-group counts at or above the plan's registered minimum.

An operator authors a protocol before inspecting either arm's outcomes:

```json
{
  "schema_version": 1,
  "experiment_id": "critic-correctness-v2",
  "activation_authorized": false,
  "dataset_sha256": "<dataset digest>",
  "plan_sha256": "<plan digest>",
  "baseline_candidate_id": "<inline route digest>",
  "candidate_candidate_id": "<skill route digest>",
  "estimand": "equal_independence_group_paired_delta",
  "stopping_rule": "fixed_complete_matrix",
  "family_scope": "three_paired_metrics_both_splits",
  "holdout_rule": "seal_before_holdout_then_evaluate_once",
  "gate": {
    "schema_version": 1,
    "max_detection_regression": 0.02,
    "max_false_positive_increase": 0.01,
    "max_completion_regression": 0.01,
    "max_mean_cost_increase_microusd": 500,
    "max_p95_latency_increase_ms": 250
  }
}
```

Negative cost or latency limits demand an improvement. `null` omits that resource
gate; it does not invent missing spend. A configured cost gate requires paired cost
coverage for every sample.

Seal it before execution or outcome inspection:

```sh
mos eval-seal-skill-comparison \
  --dataset eval/dataset.json \
  --plan private/plan.json \
  --protocol eval/skill-comparison-protocol.json \
  --output private/sealed-skill-comparison.json
```

The seal binds the protocol, dataset, plan, baseline prompt, and candidate prompt.
Changing any prompt byte, package resource, model parameter, assignment, threshold,
or dataset produces a different identity or fails verification.

## Paired scoring

Execution and grading use the existing blinded full-matrix workflow. Both routes
review the same cases and repetitions. Two independently enrolled human graders
sign route-blind per-finding decisions, conflicts require a trust-disjoint resolver,
and `eval-compile-dual` creates the source-linked observation artifact.

Calibration may be scored without consuming a holdout claim. Holdout scoring also
requires an existing mode-0700 directory that is separate from the output path:

```sh
mos eval-score-skill-comparison \
  --dataset eval/dataset.json \
  --plan private/plan.json \
  --batch private/holdout-batch.json \
  --mapping private/holdout-map.json \
  --raw-results private/holdout-raw.json \
  --grading-batch private/holdout-grading.json \
  --dual-grading-resolution private/holdout-dual.json \
  --dual-graded-observations private/holdout-observations.json \
  --grading-trust-policy policy/graders.json \
  --resolution-trust-policy policy/resolvers.json \
  --sealed-comparison private/sealed-skill-comparison.json \
  --holdout-use-directory private/holdout-claims \
  --split holdout \
  --output private/skill-comparison-report.json
```

Before verification or scoring begins, the CLI atomically creates an exclusive,
mode-0600 claim keyed by the sealed comparison. The claim binds every holdout
lineage digest. A validation failure still consumes the attempt; a second invocation
for the same seal fails. This is a local same-user control, not a distributed lock.

For detection, clean false-positive risk, and completion, the estimator works in
three stages: average repetitions within each case, calculate candidate minus
baseline for the paired case, then average case deltas within each declared
independence group. Groups receive equal weight. A two-sided Hoeffding interval uses
a Bonferroni family of six: three metrics across calibration and holdout. Detection
and completion pass when their lower bounds stay above the registered negative
margins; false-positive risk passes when its upper bound stays below the registered
increase. Repetitions do not increase the group count.

Cost is the mean of paired per-sample cost differences. Latency is the nearest-rank
p95 of paired per-sample latency differences. The report records every component,
the full dual-lineage report digest, the claim digest for holdout, and the overall
registered-gate result.

## Interpretation and limits

Passing means only that this fixed experiment met its authored thresholds. It does
not authorize changing a default persona, dispatching a model, or activating a
skill. Promotion needs a separately designed authority boundary and a policy for
multiple skill revisions, package retention, rollback, expiry, and drift.

The design assumes declared groups are genuinely independent, cases represent the
target workload, grader enrollment maps to real independent humans, and neither
prompt leaks its identity in model output. Output prose can still reveal an arm to
graders. The local claim can be deleted or bypassed by the owning OS user. Package
digests authenticate retained bytes, not authorship or instruction quality.

This milestone also changes wire contracts: `SkillIdentity`, `RouteCandidate`, and
`CandidateGrid` are schema 2, `SweepPlan` is schema 3, and `EvaluationRequest` and
`ExecutionBatch` are schema 2. Older plans and batches did not identify their exact
instructions and cannot be safely migrated; regenerate them.
