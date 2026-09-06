# Calibration-only candidate policy freezing

`eval-freeze-routing-policy` deterministically applies a sealed study's selection
rule to its authenticated profile-calibration report. The result is a candidate
policy for holdout evaluation, not a production router.

```console
mos eval-freeze-routing-policy \
  --dataset private/dataset.json \
  --plan private/sweep-plan.json \
  --batch private/calibration-batch.json \
  --mapping private/calibration-map.json \
  --raw-results private/calibration-raw.json \
  --grading-batch private/calibration-grading.json \
  --dual-grading-resolution private/calibration-resolution.json \
  --dual-graded-observations private/calibration-observations.json \
  --grading-trust-policy trusted/human-graders.json \
  --resolution-trust-policy trusted/conflict-resolvers.json \
  --feature-manifest private/prompt-features.json \
  --sealed-study private/sealed-routing-study.json \
  --calibration-report private/routing-calibration-report.json \
  --output private/frozen-candidate-policy.json
```

The command reconstructs the calibration report from every dataset, execution,
grading, trust-policy, feature, and study source before making a decision. Edited
scores or detached hashes fail rather than influencing the policy.

For each profile, the freezer:

1. restricts candidates to the role's sealed hard-floor allowlist;
2. identifies routes that passed the profile's simultaneous detection, clean-risk,
   completion, and configured latency gates;
3. requires complete cost coverage for every such permitted route;
4. applies any configured cost ceiling, then selects the minimum mean cost, p95
   latency, and candidate digest in that order; or
5. applies the sealed role fallback or fail-closed behavior when no quality route
   qualifies or any qualifying route lacks cost evidence.

Every decision records the considered allowlist, fallback identity, candidates
excluded below the floor, quality-eligible candidates, final selection-eligible
candidates, missing-cost candidates, basis, action, and selected concrete route.
Known cost-ceiling failure is distinct from missing cost. Fallback decisions do not
claim selected calibration metrics, even when the fallback had measurements.

## Deliberate limits

The artifact has literal `holdout_status: "not_evaluated"`,
`promotion_ready: false`, and `activation_authorized: false`. No runtime router
accepts it. The freezer has no split argument, provider credentials, entitlement
catalog, configuration target, or publishing capability. It cannot consume holdout
outcomes through its strict calibration-report schema.

The role floor and fallback remain reviewed operator judgments. Calibration success
does not establish holdout quality, provider availability, current pricing, drift
stability, or production safety. A separate one-time holdout evaluator must measure
coverage, under-routing, regret, detection, false positives, completion, latency,
and cost without changing this frozen artifact. Promotion and activation require
later independent authorization.
