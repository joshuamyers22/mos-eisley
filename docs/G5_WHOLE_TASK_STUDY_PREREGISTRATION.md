# G5 paired whole-task study: preregistration protocol

Status: **design recorded; study not sealed or eligible to run for a G5 claim**.
This document fixes the analysis and failure rules that can be fixed before
observing outcomes. The study-specific manifest described below must supply every
open value, receive independent review, and have its exact digest placed in an
external append-only record **before** assignment, execution, grading, or outcome
inspection. A repository commit alone proves content identity, not that timing.
No existing evaluation receipt, recorded review, or conformance probe is a G5
whole-task result. This protocol grants no simplification or runtime authority.

This implements [L5](adversarial-review-loop-project-plan.md#phase-l5--controlled-simplification-and-routing),
[R1/R2](adaptive-reasoning-routing.md#delivery-gates), and the
[G5 gate](mos-eisley-plan.md#264-delivery-order-and-accountable-gates). G3
independent utility evidence is required; a write-workflow claim additionally
requires representative G4 whole-loop evidence. Design and fixture work may
proceed while those gates are being completed.

This is the **initial paired frozen-start study**. The later
[continuous production levels](mos-eisley-plan.md#266-continuous-production-study-and-calibration)
reuse its independent grading rubric and safety outcomes but require distinct
prospective cohort and randomized live-analysis protocols. A live task receives
one user-affecting policy; it is not replayed under multiple policies to manufacture
a pair. Each later cohort has its own fresh holdout, once-used decision and
family-wide error-budget allocation. This document does not authorize those
cohorts or amend its still-unset initial-study inputs.

## Decisions and comparisons

The unit of intervention is a **complete task policy**, beginning from the same
frozen task specification and repository state and ending in a final disposition.
Count planning, all model/tool calls, readings, tests, review, repair, handoffs,
failed and abandoned attempts, and final verification. Do not compare only the
individual calls that succeeded or only tasks accepted by the author.

Four distinct comparison families are registered. Each has its own exact arm
configuration and independent result; the families are not an unregistered
factorial experiment.

| Family | Reference arm | Candidate arm(s) | Decision sought |
|---|---|---|---|
| A: Stage 0 | Deterministic checks with the otherwise identical full downstream workflow | Add two sealed independent plan readings before that same downstream workflow | Whether Stage 0 improves whole-task outcomes enough to justify its cost; overlap with later findings is descriptive only |
| B: review coverage | Frozen full roster of `N` critics plus full judge | One critic; `N` critics without judge, each with every other task rule fixed | Whether either reduced path retains detection and limits correct-work damage; experimental arms have no production acceptance authority |
| C: judge sampling | Full judge on every eligible finding | A fully specified sampled-judge policy with mandatory adjudication triggers and a known-probability audit of the ordinary path | Whether the proposed sampling rule qualifies without weakening final required checks |
| D: route cost | Frozen fixed eligible model/effort routes with full review | Each named cheaper reviewer or whole-task routing policy, including any bounded cascade as a complete policy | Whether a cheaper policy meets quality gates and saves whole-task cost |

`N`, every role/route/prompt/rubric/version, Stage-0 procedure, judge-sampling
rule and inclusion probability, fallback, cap, and comparison-specific eligible
population are **manifest inputs**. They are not inferred from a run or replaced
after outcomes. A cascade is measured from its initial decision through every
escalation; its eventual success cannot be credited as a cheap single call.
Only policies eligible under the same authority, privacy, containment and spend
rules may enter an arm. Measurement judges, graders, rubric, output contracts and
their budgets are frozen across arms within a comparison.

## Population, pairing, and assignment

Before execution, the manifest identifies the target population, task source and
sampling frame, inclusion/exclusion rules, independent-group scale, group IDs,
clean/defective strata, task and repository revision digests, and eligibility for
each comparison. Related tasks, mutations, revisions and trajectories belong to
one declared group and one data split. Missing or disputed group identity,
sampling probability, label, or split is recorded as unknown and cannot be
invented, repaired from outcomes, or used for a population gate. Hard-case
oversampling is disclosed separately from the ordinary probability sample; an
unknown inclusion probability makes population-rate claims descriptive only.

Each eligible task is assigned to all applicable arms from independent, clean
copies of the same frozen starting state. The manifest fixes the number of
repetitions, assignment/randomization algorithm, seed custody, execution-order
balance, and how provider or time effects are blocked. The manifest's arm count
and spending ceiling are checked before any paid run. Paired attempts share only
the frozen inputs; they do not share mutable files, conversation state, provider
reasoning state, correction history, or retrieved prior-task content. Assignment
and order are retained for audit. A task cannot become a fresh holdout merely by
renaming its files or changing its policy digest.

The manifest separately identifies calibration/development and once-used holdout
groups with enforced access before packet construction. Exposed regression cases,
prompts, notes, caches, templates, and policy-tuning inputs remain development
data. Policies and all thresholds freeze on development data; holdout is opened
once for the registered comparisons. Missing follow-up, unavailable execution,
and nonresponse stay visible with their original assignment and reason. There is
no replacement draw after a failure unless an exact replacement rule and its
sampling consequences were frozen in the manifest.

## Independent outcomes and denominators

Two separately authenticated, route-blind graders assess each complete task
against its frozen requirements and evidence; a trust-disjoint resolver signs
exact disagreements. The grading protocol records expected defects, emitted and
never-raised escaped defects, unnecessary requested changes, introduced
regressions, completion, and unresolved outcomes. Neither a model judge nor a
passing test is ground truth. An explicit follow-up window and ascertainment
process are manifest inputs; an unobserved follow-up is **unknown**, not clean.

Report these outcomes for each arm and paired difference:

| Outcome | Task-level definition and denominator |
|---|---|
| Defect detection | Independently established expected defects found with valid evidence / all expected defects on defective tasks; also report the fraction of defective tasks with any escaped defect |
| Completion | Tasks reaching a current, fully verified final disposition / all assigned tasks; failure, cancellation, timeout and abandonment are noncompletion |
| Requested-change damage | Initially acceptable tasks on which the loop requests an independently adjudicated unnecessary change / all independently established initially acceptable assigned tasks |
| Regression damage | Initially acceptable tasks on which the loop introduces an independently adjudicated regression / the same denominator |
| Any correct-work damage | Union of the two damage events / the same denominator; never sum the rates or use author rejections as the denominator |
| Whole-task cost | Total settled and conservatively retained uncertain spend across the complete assigned task, including retries, repairs, child work, tests and judge; no success-only denominator |
| Whole-task latency | Assignment-to-terminal wall time, including queues, pauses under the frozen policy and failures; report p50 and p95 plus timeout fraction |

Show counts and missingness by arm, clean/defective stratum, group, task source and
failure category. An unresolved correctness label or missing follow-up blocks a
positive safety claim unless the manifest's predeclared worst-case sensitivity
analysis still passes. Infrastructure failure remains a failure, not an omitted
case. A zero-verified-success arm cannot qualify on apparent cost savings.
Diagnostic stage overlap, self-consistency, citation aptness, author rejection and
judge agreement never replace the independent outcomes above.

## Analysis and decision rule

The primary estimand is the equal-weight mean across declared independent groups
in the target population. Average repetitions within task, then tasks within
group, then groups. Compute paired candidate-minus-reference differences within
the same group; related cases and repeated attempts do not increase the group
count. Report per-stratum estimates and the registered target-population estimate;
no post-result change of weights or target population is permitted.

For bounded quality outcomes, use simultaneous one-sided distribution-free bounds
on group means and paired differences. The manifest fixes the total error budget
`alpha`, the complete family of candidate arms and gated metrics, and a Bonferroni
allocation before results. For a group value in `[0, 1]`, a Hoeffding radius with
`n` independent groups and per-bound error `a` is
`sqrt(log(1/a)/(2*n))`. For a paired difference in `[-1, 1]`, the radius is
`sqrt(2*log(1/a)/n)`. Clip absolute-rate bounds to `[0, 1]` and difference bounds
to `[-1, 1]`. Use the relevant one-sided direction for each gate. This is
conservative and depends on valid group independence, representative inclusion,
correct labels, and complete registered follow-up; a tiny radius from repeated
runs within one group is invalid.

Each candidate must pass **all** applicable registered gates on the once-used
holdout: an upper bound on absolute any-damage rate; upper bounds on added damage
and escaped-defect risk; lower bounds on detection and completion relative to the
reference and any absolute floors; a lower bound on worthwhile whole-task savings;
and the registered p95 latency ceiling. The manifest gives the exact inequalities,
numeric ceilings/margins/floors, cost normalization cap and treatment of uncertain
spend, and latency cap before data collection. Cost differences require a bounded
predeclared task spending cap for a distribution-free bound; uncertain spend counts
at its held maximum unless independently settled. An exceeded cap is a policy
failure, not a reason to discard the task. The p95 criterion is reported on all
assigned tasks and is a descriptive operational gate unless the manifest freezes
a separately reviewed population-tail method.

Use one fixed sample and one planned analysis. No optional stopping, unregistered
arm deletion, threshold tuning, selective subgroup promotion, or repeated holdout
queries. If any gate is missing, underpowered, infeasible, or inconclusive, retain
the full-review/fixed-route reference. A passed comparison supports only its exact
population, policy bytes, provider versions, spending limits and follow-up window.
It does not itself activate that policy; G6 has separate signer, witness and
dispatch requirements.

## Required pre-outcome manifest and feasibility check

The manifest is a reviewed, versioned private artifact; its public record contains
only its digest and non-sensitive design metadata. It must fix, at minimum:

1. Study owner, independent evidence reviewer, grader/resolver roles, exact
   protocol revision, resource ceiling and planned dates.
2. Target population, sampling frame and probabilities, grouping rule and reviewed
   group IDs, eligibility, clean/defective labels and immutable split assignments.
3. Exact comparison family/arms, role roster and route versions, prompts/rubrics,
   fixed measurement path, Stage-0 and sampling rules, task cap and repetitions.
4. Seed and order-control procedure, frozen task/source digests, environment and
   provider versions, follow-up window, and missingness/replacement rules.
5. All numeric quality, damage, savings, latency and budget thresholds, `alpha`,
   full simultaneous comparison family, minimum independent groups per stratum,
   and a prospective sample-size and spend calculation for every gate.
6. Grading and dispute rubric, access controls, holdout custodian, storage/retention
   policy, and external append-only digest/timestamp location.

Before sealing, calculate the **attainable** bound for each proposed group count.
Even with zero observed damage, the absolute damage upper radius is at least
`sqrt(log(1/a)/(2*n))` under the chosen method. If that exceeds the damage ceiling,
the study cannot qualify at that size. Likewise calculate the best-case paired
non-inferiority and savings bounds, then total assignments, maximum spend and
follow-up workload. Do not choose a universal per-bucket count or call the minimum
group count a power calculation. If no feasible budget and sample satisfy the
registered gates, revise the design **before** outcome access and issue a new
manifest/digest; do not relax a gate after viewing results.

The current plan does **not** supply the manifest's numeric thresholds, group IDs,
sampling probabilities, labels, split assignments, sample size, provider roster or
budget. This document does not fill them. Until a reviewed complete manifest is
externally time-attested before outcomes, the study status remains **unsealed** and
no G5 qualification claim is permitted.
