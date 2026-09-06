# Group-aware evaluation adversarial review

Scope: group declarations, split integrity, confidence intervals, comparison
families, statistical gate behavior and schema migration.
Reviewer: implementing assistant self-review, without independent statistical
review or live-provider measurements.

## Findings resolved

| Impact | Finding | Implemented control |
|---|---|---|
| High | Repeating one clean and one defective case can pass a pooled Wilson gate | Gate on independent group averages; repeated rows do not add groups |
| High | Many route comparisons increase the chance of a spurious pass | Allocate 0.05 across all planned routes, three metrics and both splits |
| High | Related cases can leak from calibration into holdout | Reject groups shared across splits and exact duplicate briefs |
| High | Missing group metadata could silently imply case independence | Return diagnostics with explicit ineligibility instead of inferring independent units |
| Medium | Silent failures appear to improve clean false-positive performance | Treat failed clean reviews as worst-case risk in the gating metric |
| Medium | Groups with many related cases can dominate the quality estimate | Average repetitions, then cases, then groups with equal group weights |
| Medium | A passing fixture report can be mistaken for a calibrated router | Every report and CLI summary states promotion_ready=false |
| Medium | A method change silently reinterprets old artifacts | Version dataset, gate, plan and report schemas; require regenerating the chain |

## Evidence

Regression tests cover repeated-case invariance, known analytic bounds, sufficient
independent groups, increased comparison-family width, group/split leakage,
duplicate briefs, unequal group sizes, failed clean reviews, invalid rates and
unsupported stopping rules. Existing artifact-chain and end-to-end CLI tests remain.

## Open issues

- Declared groups may still be correlated, incorrectly labeled or unrepresentative.
- The conservative finite-sample bound can require a large evaluation dataset.
  Minimum group count does not establish power.
- Cost and latency gates describe recorded observations, without population bounds.
- Local artifacts cannot enforce pre-registration, single-use holdout access,
  authenticated grading or an error budget across separately authored plans.
- A per-sample detection list does not yet link every emitted finding to a specific
  expected defect. Inter-rater agreement and dispute resolution remain unimplemented.
- Fixture execution is not evidence of live-model quality or process isolation.

Next milestone: per-finding adjudication and agreement, then isolated live execution
and a pre-registered representative sweep before any routing policy is promoted.
