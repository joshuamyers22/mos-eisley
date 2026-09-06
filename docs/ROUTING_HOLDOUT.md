# Frozen-policy holdout evaluation

`eval-evaluate-routing-holdout` measures an immutable candidate policy against the
exact authenticated holdout matrix. It does not refit the policy, call a provider,
promote a result, or activate runtime routing.

Before scoring begins, the command atomically creates
`<candidate-policy-sha256>.json` in an existing operator-supplied claim directory.
That directory must be owned by the current user, grant no group/other permissions,
and be separate from the report path. An existing claim fails closed. A failed or
interrupted attempt remains consumed so a disappointing result cannot be retried
through the same local control.

```console
mkdir -m 700 private/holdout-claims
mos eval-evaluate-routing-holdout \
  --dataset private/dataset.json \
  --plan private/sweep-plan.json \
  --feature-manifest private/prompt-features.json \
  --sealed-study private/sealed-routing-study.json \
  --calibration-report private/routing-calibration-report.json \
  --candidate-policy private/frozen-candidate-policy.json \
  --calibration-batch private/calibration-batch.json \
  --calibration-mapping private/calibration-map.json \
  --calibration-raw-results private/calibration-raw.json \
  --calibration-grading-batch private/calibration-grading.json \
  --calibration-dual-grading-resolution private/calibration-resolution.json \
  --calibration-dual-graded-observations private/calibration-observations.json \
  --calibration-grading-trust-policy trusted/human-graders.json \
  --calibration-resolution-trust-policy trusted/conflict-resolvers.json \
  --holdout-batch private/holdout-batch.json \
  --holdout-mapping private/holdout-map.json \
  --holdout-raw-results private/holdout-raw.json \
  --holdout-grading-batch private/holdout-grading.json \
  --holdout-dual-grading-resolution private/holdout-resolution.json \
  --holdout-dual-graded-observations private/holdout-observations.json \
  --holdout-grading-trust-policy trusted/human-graders.json \
  --holdout-resolution-trust-policy trusted/conflict-resolvers.json \
  --holdout-use-directory private/holdout-claims \
  --output private/routing-holdout-report.json
```

The evaluator fully reconstructs the frozen policy from calibration sources, then
reverifies the separate holdout execution and dual-grade lineage. It requires exact
holdout assignment coverage and uses the pre-registered confidence family across
all profiles, routes, metrics, and both splits.

For every sealed profile, the report preserves all route scores and the frozen
decision. It records:

- holdout-adequate candidates inside the sealed role floor;
- whether the selected route was adequate;
- under-routing, defined as a selected route failing while another permitted route
  passed (the protocol does not invent a post-hoc model-strength ordering);
- fail-closed profiles that missed an adequate alternative;
- fallback and calibrated-route coverage; and
- cost and latency regret against the cheapest adequate route, ordered by mean
  cost, p95 latency, then candidate digest.

If any adequate route lacks complete cost evidence, the report names those routes
and emits neither a cheapest-route nor regret claim for that profile. Cost and
latency remain descriptive observed summaries, not population confidence bounds.

## Trust boundary

The claim is a crash-conservative local guard, not a global secrecy system. A user
who controls the files can copy the holdout, choose another claim directory, delete
claims, invoke the pure library function, or inspect outcomes separately. Enforce
true one-time access with an independent data custodian or append-only service and
archive the claim beside the report. The content digest proves exact bytes, not when
the protocol or claim was created.

The report has literal `promotion_ready: false` and
`activation_authorized: false`; no runtime router accepts it. Promotion still needs
independent authorization, operational availability and pricing validation, drift
controls, and representative credentialed evaluation.
