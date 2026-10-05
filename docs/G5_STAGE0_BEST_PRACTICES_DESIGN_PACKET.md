# G5 Stage-0 paired study: best-practices design packet

Status: **design proposal for owner, custodian and independent statistical review;
not an approved manifest, seal, execution authorization or G5 result**.
Prepared 2026-09-26 from the [G5 preregistration protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md),
[candidate decision gates](G5_STAGE0_GATE_PROPOSAL.md) and
[source audit](G5_STAGE0_MANIFEST_SOURCE_AUDIT.md). This packet specifies a
prospective method for obtaining and checking missing manifest inputs. It contains
no task roster, group assignments, labels, split mapping, prompts, transcripts,
model responses, tool output or outcomes. Sampling receipts are metadata only.

## Decision and scope

Study **family A only**: compare complete tasks from isolated copies of the same
frozen start. The reference runs deterministic checks and the full downstream
workflow. The candidate adds two sealed independent plan readings before that
same downstream workflow. Count all planning, production review, repair, retries,
failed and abandoned work in each arm's whole-task outcome under the
[registered denominators](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md#independent-outcomes-and-denominators).
Independent study grading and follow-up are separately budgeted measurement work.
Use the same pinned independent grading rubric in both arms and later production
levels. This study has one candidate, one fixed horizon, one holdout opening and
one all-required qualification decision. It gives no authority to remove review
or alter production routing. G3 evidence, and representative G4 whole-loop
evidence for write workflows, remain separate entry conditions.

The claim targets an **equal-weight mean of independent groups in the declared
population**. State that population precisely: a finite frozen eligible group
frame is the recommended first study target. Its result is about that frame;
extension to future production tasks requires a separately justified population
model or the prospective live cohort design in
[plan §26.6](mos-eisley-plan.md#266-continuous-production-study-and-calibration).

## Custodian-built frame and draw

1. A data custodian who cannot grade or promote freezes a private frame before
   assignment. Group all related tasks, mutations, revisions and trajectories at
   the approved independence scale. Record each group's identity and source
   digests, eligibility, pre-established clean/defective task labels, exposure
   history and immutable development/holdout placement. The custodian obtains
   labels through the approved independent adjudication workflow; unknown or
   disputed labels remain unknown. Labels and strata are withheld from the arm
   executors. No code here derives IDs, labels or splits from a sampling receipt
   or outcome.
2. Keep development groups previously exposed to policy tuning outside the
   once-used holdout. For the first study, define the target finite population
   as the eligible holdout frame frozen before sampling. A claim about all future
   owner traffic would need a different source and design. Report frame coverage
   and exclusions so a narrow frame cannot be described as general production.
3. As a **candidate sampling design**, partition holdout groups by pre-outcome
   task eligibility into clean-only, defective-only and mixed strata. Each group
   appears in exactly one stratum; a mixed group retains all its related tasks.
   Freeze each stratum size `N_h` and intended sample size `n_h`, then draw `n_h`
   groups uniformly without replacement from that stratum using a custodian-held
   random seed. For a group in stratum `h`, its inclusion probability is
   `pi_i = n_h/N_h`; for two distinct groups in the same stratum it is
   `pi_ij = n_h(n_h-1)/(N_h(N_h-1))` when `N_h > 1`. Across independently drawn
   strata, `pi_ij = pi_i*pi_j`. Record the exact realized draw privately.
   These formulas describe a proposed draw; they do **not** supply actual
   probabilities or assignments. [Horvitz–Thompson](https://doi.org/10.1080/01621459.1952.10483446)
   and [CDC survey-weight guidance](https://wwwn.cdc.gov/nchs/nhanes/tutorials/weighting.aspx)
   explain why unequal inclusion must be reflected in population estimates.
4. For each metric, define its eligible group domain before sampling. Clean-risk
   gates use groups containing independently established initially acceptable
   tasks; defective-task gates use groups containing defective tasks; completion,
   cost and latency use all assigned groups. Average repetitions within task,
   tasks within group, then apply the design-matched group estimator. Within a
   domain `D`, a proposed stratified finite-frame mean is
   `sum_h (N_h,D/N_D) * sample_mean_h,D`, using only strata in which all groups
   qualify for `D`. The custodian must supply `N_h,D` and the reviewer must
   verify that the eligibility partition makes this expression valid. Apply the
   same weights to within-group paired differences. Report stratum estimates
   separately. A selected hard-case channel is diagnostic and stays separate.

If the approved frame cannot support this partition, do not force the formula.
The reviewer must specify a different probability design, its exact inclusion
probabilities, target estimator and valid confidence method **before** the draw.
[Serfling](https://doi.org/10.1214/aos/1176342611) and
[Bardenet–Maillard](https://doi.org/10.3150/14-BEJ605) address uniform draws
without replacement; the independent-draw
[Maurer–Pontil](https://www.cs.mcgill.ca/~colt2009/papers/012.pdf) radius cannot
simply be relabeled as a finite-frame bound. If the entire finite frame is
observed, its finite-frame mean is known exactly, but that alone proves nothing
about a broader population.

## Frozen measurement and claim

- Freeze the exact task/arm, environment, route, measurement-judge and rubric
  digests; the common enforced per-task spend cap `B`; task deadline; follow-up
  window; randomization/order balancing; and maximum repetitions before any
  execution. Keep both arm runs isolated. Two separately authenticated,
  route-blind graders receive the same frozen rubric; a trust-disjoint resolver
  signs exact disagreements. Keep grading identities and private labels outside
  sampling metadata. Specify whether the estimand averages over provider/model
  execution randomness or covers only the sealed execution protocol's realized
  attempts. Repetitions and time blocking must match that estimand. A finite-frame
  sampling inequality for fixed group values alone does not establish coverage
  for additional stochastic execution or provider drift; the reviewer must
  justify the combined uncertainty before selecting the interval.
- Select **one** benefit outcome and minimum useful improvement `beta_min` from
  the fixed rubric using independent development evidence and the owner's
  explicit value judgment. Earlier defect prevention makes reduced escaped-defect
  task risk a plausible candidate, but it is not selected by this packet. Record
  the benefit direction and numeric `beta_min` before holdout access. No generic
  statistical source can determine the project's worthwhile effect size.
  [ICH E9(R1)](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf)
  supports aligning the estimand, missing outcomes and sensitivity analysis
  before measurement.
- Retain the proposal's seven safety gates and candidate `1.10` maximum
  whole-task cost ratio and `1.20` observed p95 latency ratio for independent
  review. For cost, bound the one paired group contrast
  `(candidate_cost - 1.10*reference_cost)/B`, whose range is `[-1.10,1]` if both
  arm costs stay in `[0,B]`. A cap breach fails the cost gate and remains in the
  assigned-task record; never clip actual cost into that range. p95 is an
  observed operational gate unless a separate population-tail method is sealed.
- Treat all assigned tasks by intent to treat. Failure, cancellation, timeout and
  abandonment count as noncompletion and in whole-task cost. Unresolved
  correctness or follow-up is unknown; apply the predeclared worst-case
  sensitivity rule. For an upper harm comparison, unknown candidate outcomes
  take the harmful value and unknown reference outcomes the favorable value;
  reverse the choices for a lower benefit comparison. Do not replace failed
  assignments or declare missing follow-up clean.

The proposed statistical claim is one **all-gates-must-pass** Stage-0 decision at
one-sided `alpha = 0.05`. Under an independently reviewed intersection-union rule,
each statistical gate can be tested at that level because one failure defeats the
single claim. This does not provide simultaneous 95% coverage for separately
reported gate estimates, permit choosing a favorable benefit endpoint, or cover
another candidate/cohort. Allocate error separately for any such additional
claims. [FDA's final multiple-endpoints guidance](https://www.fda.gov/media/162416/download)
explains the all-required versus multiple-path distinction.

For the proposed finite-frame stratified draw, review a one-sided
empirical-Bernstein–Serfling interval for each bounded group value and paired
difference. In [Bardenet–Maillard Theorem 4.3](https://arxiv.org/pdf/1309.4029),
the coverage statement is at least `1 - 5*delta`: for a gate-level error `a`
divided across `H` contributing strata by a conservative union bound, set
`delta_h = a/(5*H)` and aggregate stratum bounds with the frozen nonnegative
population weights. Transform `[-1,1]` differences, and the cost contrast's
`[-1.10,1]` range, to `[0,1]` before applying a bound, then map back. A census
stratum uses its exact finite-frame mean. The reviewer must check the theorem's
`n_h`, `N_h`, variance, direction and edge-case conditions and approve the
combined bound implementation. If that review fails, use a separately validated
conservative design-matched method. Do not pick a method by viewing holdout
outcomes. The fixed-horizon bound cannot justify favorable interim looks.

## Feasibility before any paid assignment

The independent statistical reviewer calculates best-case attainable bounds and
prospective **joint** pass probability under independently available development
assumptions for group heterogeneity, paired effects, reference rates, missing
follow-up and cost. Freeze the assumed effect sizes, simulation code/seed and
acceptance power target before the holdout draw; report sensitivity to adverse
but plausible assumptions. A zero-variance illustration is not power. The
reviewer must check every clean, defective and all-task gate, including the
chosen `beta_min` and normalized cost contrast, at the actual proposed `N_h,n_h`.

Calculate task assignments from the actual group roster and repetitions:
  `A = 2 * sum_selected_groups(sum_tasks_in_group(repetitions_per_task))` for the
two arms. Check the plan's current 5,000-case and 50,000-assignment evaluator
ceilings unless a separately approved implementation changes them. With the task
cap enforced, `A*B` is a conservative upper bound on paid task exposure; add
independently priced grading, resolution, follow-up, storage and a contingency
for enforcement failure to the owner's total authorized
ceiling. Route prices, `B`, workload and the budget owner must be fixed from
approved route/conformance evidence and current provider terms. If any gate is
unattainable within the approved group supply, workload or budget, record an
inconclusive design and revise prospectively; do not pool related groups,
weaken a threshold or inspect the holdout to rescue it.

## Review, seal and handoff

| Step | Required evidence before the next step |
|---|---|
| 1. Custodian freeze | Private frame and group/label/split artifacts, exact hashes, stratum sizes and draw procedure; no study-arm outcome access |
| 2. Owner decision | Exact benefit outcome and `beta_min`, safety/cost/latency limits, eligible routes and price terms, enforced cap and total spending authority |
| 3. Independent review | Signed sampling/estimand/interval and multiplicity review; feasible joint power, assignment, grading and spend calculations; grader/resolver and owner role separation |
| 4. Private manifest freeze | Canonical exact manifest with every required field populated; no null placeholder or unapproved conditional branch; source digests and access controls verified |
| 5. External pre-outcome seal | Post **only** the exact manifest digest and permitted safe metadata to a reviewed independent append-only location; retain and verify timestamp, signer and inclusion/consistency proof before assignment |
| 6. Execution and one analysis | Draw/assign exactly as sealed, retain failures and unknowns, dual-grade blindly, wait for follow-up maturity, then open the holdout once for the registered fixed-horizon decision |

[Rekor's documented transparency log](https://docs.sigstore.dev/logging/overview/)
is an append-only candidate; [RFC 3161](https://www.rfc-editor.org/info/rfc3161/)
specifies a signed time-stamp token. The owner and independent reviewer must
approve the actual operator, identity and privacy exposure. A timestamp by itself
is not an append-only log; a local commit or hash does not establish a pre-outcome
seal. Do not publish the private manifest or any task/label content.

Before use, exercise fail-closed fixtures for duplicate/related groups, a mixed
group, a changed label or split, bad/missing inclusion probability, n=1 and
census strata, incomplete pairs, unresolved and late outcomes, zero verified
successes, cost cap breach, stale source digest, reviewer/role overlap, missing
external receipt and attempted second holdout opening. The initial study's
private manifest stays **incomplete and unsealed** until the cited evidence is
actually supplied, independently approved and externally time-attested.
