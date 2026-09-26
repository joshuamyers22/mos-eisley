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
| A: Stage 0 | Deterministic checks with the otherwise identical full downstream workflow | Add two sealed independent plan readings before that same downstream workflow | Whether a prespecified independently graded benefit exceeds its minimum useful effect while safety and maximum added whole-task cost pass; overlap with later findings is descriptive only |
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
one declared group and one data split. The manifest also chooses the sampling
regime before assignment: independent draws from a stated group population,
probability sampling without replacement from a fixed finite group frame, or a
separately reviewed design. It fixes stratum allocation and the draw law or
finite-frame inclusion probabilities as applicable, including joint inclusion
probabilities when the variance method needs them. The approved estimator and
interval must target the declared population under that exact regime. An
unweighted sample mean estimates the equal-weight population-group mean only
when the sampling design supports it;
unequal-probability or stratified draws require predeclared design weights or a
separately justified estimator. Review
[Horvitz–Thompson](https://doi.org/10.1080/01621459.1952.10483446) for unequal
inclusion and [Serfling](https://doi.org/10.1214/aos/1176342611) for a finite
frame without replacement where applicable. Selected hard cases have a separate
channel and cannot be silently pooled with the ordinary probability sample.
Missing or disputed group identity, sampling probability, label, or split is recorded as
unknown and cannot be invented, repaired from outcomes, or used for a population
gate. An unknown inclusion probability makes population-rate claims descriptive
only.

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
group, then apply the manifest's predeclared population estimator to group values
and paired candidate-minus-reference group differences. Related cases and repeated
attempts do not increase the group count. Report per-stratum estimates and the
registered target-population estimate; no post-result change of weights or target
population is permitted. Paired estimators retain the within-group covariance.

The exact fixed-horizon one-sided method is a manifest input requiring independent
statistical review. For genuinely independent identically distributed bounded
group draws, review a
[group-level empirical-Bernstein bound](https://www.cs.mcgill.ca/~colt2009/papers/012.pdf)
using the published sample-variance definition and remainder; a paired difference
in `[-1, 1]` must be transformed to `[0, 1]` and its interval mapped back.
Hoeffding is the
conservative compatible fallback. Neither bound automatically covers a fixed
finite-frame draw without replacement, unequal-probability sampling, correlated
groups, selective labels or missing follow-up. Use a separately reviewed
design-matched estimator and interval in those cases; do not substitute a smaller
independent-draw radius. For reference, under an applicable independent-draw
Hoeffding method the one-sided radii are `sqrt(log(1/a)/(2*n))` for `[0, 1]`
and `sqrt(2*log(1/a)/n)` for `[-1, 1]`. Clip absolute-rate bounds to `[0, 1]`
and difference bounds to `[-1, 1]`. Repetitions within one group do not narrow a
group-level bound as if they were fresh groups.

For one prespecified candidate and one **all-gates-must-pass** qualification
claim, the manifest may use an intersection-union decision: test each required
one-sided gate at the same prespecified claim error level `alpha`, and qualify
only if every gate passes. This controls false qualification for that single
conjunctive statistical claim; it does not give simultaneous coverage for the
individual reported intervals, make descriptive p95 a population claim, or
permit choosing a favorable endpoint. Additional candidate
policies, alternative benefit endpoints, separately asserted metric claims and
successive holdouts require a precommitted family-wide allocation or another
independently reviewed multiplicity procedure. A Bonferroni allocation remains
the conservative option for simultaneous interval claims. The
[FDA's co-primary endpoint guidance](https://www.fda.gov/media/162416/download)
supports this distinction between one all-required decision and multiple paths
to success; the transfer still needs study-specific statistical review. Freeze
the claim type, all gate directions, methods and allocations before outcomes.

Each candidate must pass **all** applicable registered gates on the once-used
holdout: an upper bound on absolute any-damage rate; upper bounds on added damage
and escaped-defect risk; lower bounds on detection and completion relative to the
reference and any absolute floors; and the registered p95 latency ceiling. Family
A additionally requires one preselected independently graded benefit endpoint to
exceed its minimum useful effect and an upper bound on added whole-task cost below
its maximum. Families B–D require a lower bound on worthwhile whole-task savings.
The manifest gives the exact inequalities, numeric benefit, cost, safety and
latency thresholds, cost normalization cap and treatment of uncertain spend before
data collection. Test a relative cost requirement through one prespecified paired
group contrast, for example `0.90*reference_cost - candidate_cost > 0` for at
least 10% savings or `candidate_cost - 1.10*reference_cost < 0` for at most 10%
added cost. Apply the design-matched one-sided bound to that single contrast;
do not silently divide by a random estimated reference mean or count its two
components as separate unadjusted claims. Cost bounds require a common enforced
task spending cap; uncertain spend counts at its held maximum unless independently
settled. A cap breach remains recorded with the assigned task and fails the cost
gate; its actual cost must not be clipped to make the bound appear valid. The p95
criterion is reported on all assigned tasks and is a
descriptive operational gate unless the manifest freezes a separately reviewed
population-tail method.

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
2. Target population, sampling regime, draw law or finite-frame inclusion
   probabilities and any needed joint probabilities, stratum allocation and population
   weights, grouping rule and reviewed group IDs, eligibility, clean/defective
   labels and immutable split assignments.
3. Exact comparison family/arms, role roster and route versions, prompts/rubrics,
   fixed measurement path, Stage-0 and sampling rules, task cap and repetitions.
4. Seed and order-control procedure, frozen task/source digests, environment and
   provider versions, follow-up window, and missingness/replacement rules.
5. All numeric quality, damage, Stage-0 benefit and maximum added cost, later-arm
   savings, latency and budget thresholds; the exact design-matched estimator and
   one-sided interval for each gate; `alpha`, the single-claim or simultaneous
   claim scope and cross-candidate allocation; minimum independent groups per
   stratum; and a prospective power, sample-size and spend calculation for every
   gate and the joint decision.
6. Grading and dispute rubric, access controls, holdout custodian, storage/retention
   policy, and external append-only digest/timestamp location.

Before sealing, calculate the **attainable** bound for each proposed group count
under the selected method and sampling regime. Under Hoeffding's independent-draw
method, even zero observed damage has upper radius
`sqrt(log(1/a)/(2*n))`; a zero-variance empirical-Bernstein benchmark has a
different nonzero remainder and is not a power calculation. Calculate prospective
joint-decision power using independently available development assumptions for
variance, reference rates, treatment effects, cost and missing follow-up. Include
best-case and plausible paired safety, Stage-0 benefit/added-cost or later-arm
savings bounds, then total assignments, maximum spend and follow-up workload. Do
not choose a universal per-bucket count or call the minimum group count a power
calculation. If no feasible budget and sample satisfy the
registered gates, revise the design **before** outcome access and issue a new
manifest/digest; do not relax a gate after viewing results.

The current plan does **not** supply the manifest's numeric thresholds, group IDs,
sampling probabilities, labels, split assignments, sample size, provider roster or
budget. This document does not fill them. Until a reviewed complete manifest is
externally time-attested before outcomes, the study status remains **unsealed** and
no G5 qualification claim is permitted.

A [Stage-0 decision-gate proposal](G5_STAGE0_GATE_PROPOSAL.md) records candidate
safety and cost thresholds, the single-claim testing option and its remaining
benefit and feasibility inputs. It is not an approved manifest or a replacement
for the missing inputs above.
