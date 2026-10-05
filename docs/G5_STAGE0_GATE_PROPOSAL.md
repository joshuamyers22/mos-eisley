# G5 Stage-0 paired study: proposed decision gates

Status: **proposal for independent review; not a study manifest or seal**.
This narrows the first G5 study to family A in the
[paired whole-task protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md): the same
frozen tasks and downstream full-review workflow with deterministic checks alone
versus deterministic checks plus two sealed independent plan readings. Families
B–D need separate prospective manifests and reviewed claim and cross-candidate
error allocations before outcomes. No probability, group, label, split, task roster,
provider route, owner, reviewer, spend authorization or external timestamp is
supplied or inferred here.

These safety numbers are **candidate decisions**, not empirical findings or a
claim that the design is affordable. A Stage-0 minimum useful benefit is still
unselected; it cannot be chosen from the holdout. An independent
statistical/evidence reviewer and the project owner must assess the full design
before a complete pre-outcome manifest is sealed.
The current grading rubric, outcome definitions, paired group estimand, full
whole-task cost denominator and unknown-outcome treatment remain as specified in
the protocol. The rubric digest must be bound in the actual manifest.

## Proposed primary gates

Use one fixed holdout analysis, one candidate arm and one prespecified
**all-gates-must-pass Stage-0 qualification claim** at one-sided `alpha = 0.05`.
Subject to independent statistical review, test each required gate at `alpha =
0.05` and qualify only if every gate passes: this is an intersection-union
decision, not nine simultaneous 95% confidence statements. Report each estimate
and interval with its claim scope. If individual metrics will be certified,
another candidate or benefit endpoint can qualify, or the study will be repeated,
register a family-wide allocation before outcomes; Bonferroni remains the
conservative simultaneous-interval option. The exact group estimator and
one-sided bound must match the reviewed sampling regime. For independent
identically distributed group draws, review empirical Bernstein first, with
Hoeffding as the conservative compatible fallback. A finite-frame or
unequal-probability sample needs a separately reviewed design-matched method.
The safety gates are evaluated before any benefit or cost conclusion.

| Gate | Proposed pass threshold | Groups with that outcome |
|---|---|---|
| 1. Absolute any correct-work damage in Stage 0 | One-sided upper bound at most 2% | Independently established initially acceptable tasks |
| 2. Added any correct-work damage | Upper bound on Stage-0 minus reference at most +1 percentage point | Paired initially acceptable tasks |
| 3. Added escaped-defect task risk | Upper bound on Stage-0 minus reference at most +1 percentage point | Paired defective tasks with completed registered follow-up |
| 4. Defect-detection loss | Lower bound on Stage-0 minus reference at least -2 percentage points | Paired defective tasks |
| 5. Absolute defect detection in Stage 0 | Lower bound at least 90% | Defective tasks |
| 6. Completion loss | Lower bound on Stage-0 minus reference at least -2 percentage points | All paired assigned tasks |
| 7. Absolute Stage-0 completion | Lower bound at least 95% | All assigned tasks |
| 8. Independently graded Stage-0 benefit | One preselected rubric outcome and minimum useful improvement `beta_min` must pass a one-sided bound; endpoint, direction and `beta_min` are mandatory pre-outcome manifest inputs | The endpoint's applicable paired groups |
| 9. Maximum added whole-task cost | Upper bound on the paired group mean of `(Stage-0 cost - 1.10*reference cost)/B` below zero; proposed maximum is 10% above reference mean | All paired assigned tasks, including failures and abandoned work |

Gate 8 can use only one benefit endpoint chosen from the fixed independent rubric
on independent development evidence. Examples are fewer escaped-defect tasks,
better defect detection or fewer damaged initially acceptable tasks; no
after-the-fact choice among them is allowed. Without a justified numeric
`beta_min` and prospective power calculation, Stage 0 has no positive utility
claim. The safety gates cannot be traded for a larger benefit or lower cost.

For gate 9, apply a valid one-sided group-level bound directly to the single
paired contrast. With both arm costs in `[0,B]`, the contrast lies in
`[-1.10,1]`; transform that entire range correctly for a bounded-value method.
`B` is the same enforced per-task cap in both arms. Uncertain spend counts at its
held maximum. A cap breach remains in the assigned-task record and fails the cost
gate; actual cost must not be clipped to preserve a false bounded-range claim.
The 10% maximum is a candidate, not a cost authorization. The actual reference
cost relative to `B`, variation and any Stage-0 rework savings determine
attainable power. A zero-success arm is ineligible regardless of cost.

The proposed operational gate is Stage-0 p95 whole-task latency no more than
`1.20 * reference p95`, with both p95 values computed on every assigned task and
timeouts counted at the manifest's task deadline. This is a descriptive gate,
not a population tail confidence claim. The manifest must also fix an absolute
task deadline, report timeout fraction, and state whether the task population
can tolerate that latency. Requested-change damage and introduced-regression
damage remain separately reported in addition to the union gated above. Missing
or disputed labels and follow-up remain unknown; they cannot be counted as clean
or quietly dropped. A positive decision also requires the protocol's predeclared
worst-case missingness sensitivity analysis to pass.

## Feasibility and method comparison

Under the former nine-way Bonferroni/Hoeffding design, even **zero** observed
damage needed 6,492 independent clean groups for gate 1; an observed paired
difference of exactly zero needed 103,860 applicable groups for a one-point
non-inferiority margin. These are historical comparisons for the superseded
proposal, not requirements for the new claim. Repetitions or related cases
cannot increase the independent-group count.

For the proposed **single** intersection-union qualification claim, each one-sided
gate can use `a = 0.05` if the claim scope is accepted. Under applicable
independent-draw Hoeffding bounds, zero observed damage still needs
`ceil(log(20)/(2*0.02^2)) = 3,745` clean groups to place gate 1 at 2%; an observed
paired difference of zero still needs
`ceil(2*log(20)/0.01^2) = 59,915` applicable groups for either one-point margin.
The paired requirement alone exceeds the current 5,000-case evaluator cap. A
fixed-horizon group-level empirical-Bernstein bound can be narrower if the
observed group variance is low, but its zero-variance remainder is not a
prospective power estimate. Unequal-probability and without-replacement sampling
need their own valid calculations; neither bound can be applied mechanically.

The main plan cites a **5,000-case** dataset cap and **50,000-assignment** cap
for the existing evaluator in
[§26.3](mos-eisley-plan.md#263-routing-and-measurement-contract). The proposed
Stage-0 gate therefore **cannot be sealed as feasible under Hoeffding**, even
with the single-claim error allocation. The 30-group default in the existing
offline statistical design is an operational floor, not a substitute for a
prospective power and cost calculation. The missing `beta_min` and sampling
design additionally block a complete Stage-0 decision rule.

Before sealing, an independent reviewer must approve the claim scope and a
design-matched group-aware method, then recalculate attainable power, assignments,
cost and follow-up load from independent development assumptions, the approved
population and route prices. Do not relax a gate, pool sparse groups, reuse a
holdout, or switch methods after seeing outcomes. A revised proposal gets a new
digest and review before any execution.

The [primary-source method review](G5_STATISTICAL_SOURCE_REVIEW.md) evaluates
variance-sensitive, binomial, paired and sequential alternatives and their
assumptions. It changes no gate or authority by itself. Families B–D keep
prespecified whole-task **savings** gates; a relative 10% saving can be tested
with one bounded paired group contrast `0.90*reference cost - candidate cost > 0`
under its own reviewed design and multiplicity allocation.

## Still required for a seal

The exact study manifest needs an approved sampling regime and frame, draw law or
finite-frame inclusion and any required joint probabilities, design weights or
estimator; reviewed independent-group rule and group IDs; clean/defective labels
and immutable split assignments; frozen task/arm/provider/rubric digests;
randomization and order rules; preselected benefit endpoint and `beta_min`, task
deadline, cap `B`, total spend ceiling and expected sample/follow-up workload;
claim/multiplicity scope, independent reviewer and grader/resolver identities;
and an independently controlled append-only location for the exact
manifest digest before assignment or outcome inspection. Those values are absent
from approved project documents. This proposal neither supplies them nor reads
any sampling registry, custodian mapping, label store or outcome store.
