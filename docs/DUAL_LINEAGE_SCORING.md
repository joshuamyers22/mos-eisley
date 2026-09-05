# Dual-lineage scoring

Mos Eisley can calculate its existing fixed-matrix statistical metrics from a
`DualGradedObservationSet` only after reconstructing and reverifying the complete
source chain. The `eval-score-dual` command requires every source artifact rather
than treating an observation-file hash as proof of provenance.

```console
mos eval-score-dual \
  --dataset eval/dataset.json \
  --plan private/holdout-plan.json \
  --batch private/holdout-batch.json \
  --mapping private/holdout-map.json \
  --raw-results private/holdout-raw.json \
  --grading-batch private/holdout-grading.json \
  --dual-grading-resolution private/holdout-dual-resolution.json \
  --dual-graded-observations private/holdout-dual-observations.json \
  --grading-trust-policy trusted/human-graders.json \
  --resolution-trust-policy trusted/conflict-resolvers.json \
  --split holdout \
  --output private/holdout-dual-report.json
```

Before computing metrics, the command rechecks the dataset and full sweep plan,
execution batch and private mapping, raw results, reconstructed grading packet,
both grader signatures, resolver policy separation and signature, derived resolved
judgments, and exact observations. It then requires the observation keys to equal
the requested split's complete case × route × repetition matrix.

The authenticated and rehearsal paths share the same statistical calculation
implementation after their different provenance checks. This prevents formula
drift while keeping their artifact contracts distinct.

`DualLineageEvaluationReport` records the dataset, plan, execution batch, mapping,
raw-result, grading-batch, both trust-policy, dual-resolution and dual-observation
digests. It repeats the registered gate and route scores. The report can be fully
recomputed with `verify_dual_lineage_evaluation_report` and is exclusively created
with mode 0600 by the CLI.

## No promotion authority

Every report has literal `promotion_ready: false`. A route's `eligible` field means
only that its measurements pass the configured statistical, cost and latency checks
for this one report. It does not activate, recommend or freeze a routing policy.
The command has no provider, registry mutation, configuration write or publishing
capability.

Cryptographic grading lineage does not establish representative data, correct
labels, grader independence, valid independence groups, safe repeated holdout use,
provider stability or production readiness. Credentialed conformance, a
pre-registered calibration/holdout decision protocol, policy derivation and a
separately authorized activation boundary remain required.
