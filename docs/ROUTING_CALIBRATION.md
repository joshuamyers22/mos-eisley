# Profile-aware routing calibration

`eval-score-routing-calibration` computes route evidence for every prompt profile
in a sealed routing study. It is deliberately calibration-only and cannot select,
freeze, evaluate, promote, or activate a routing policy.

```console
mos eval-score-routing-calibration \
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
  --output private/routing-calibration-report.json
```

Before calculating metrics, the command reconstructs and verifies the sealed study,
feature join, full sweep plan, blinded execution, private map, raw results, grading
packet, both authenticated grades, independent resolution, and derived observations.
The observations must exactly cover the calibration case × route × repetition
matrix. Holdout observations fail that equality check; there is no split option.

Cases are partitioned using the sealed numeric boundaries and exact categorical
features. Every plan route is scored in every profile. The group-aware confidence
family expands to
`profile_count * route_count * 3 metrics * 2 splits`, even though only calibration
outcomes are inspected now. Each profile score records the partition count, family
scope, and family size and validates those against every route assessment.

## Deliberate limits

Both `promotion_ready` and `activation_authorized` are literal `false`. The report
contains no selected route. It does not apply the role allowlist or choose the
cheapest candidate; scoring every planned route is necessary to preserve the
pre-registered comparison family. A later calibration-only freezer must ignore
routes outside the profile's role floor, require complete cost evidence for every
quality-eligible candidate, and fall back or fail closed when calibration is
insufficient.

The command does receive the complete pre-registered dataset and plan to verify
their digests, but it accepts outcomes for the calibration matrix only. Source code
cannot prove that an analyst has not separately accessed holdout files. Protected
storage, external pre-registration attestation, representative samples, correct
labels, and valid independence groups remain operator responsibilities.
