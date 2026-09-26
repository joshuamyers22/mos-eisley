# G5 statistical method source review

Status: research review, revised 2026-09-26. No approved method, manifest seal, outcome
access or production authority follows from this document. It evaluates primary
statistical sources for the [Stage-0 gate proposal](G5_STAGE0_GATE_PROPOSAL.md)
and the [G5 paired-study protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md).
The independent grading rubric and safety outcomes stay fixed. The missing
sampling frame, probabilities, group IDs, labels, splits, routes, spend ceiling
and independent reviewer are not supplied or inferred here.

## What the current bound establishes

The former proposal allocated one-sided `alpha = 0.05/9` per bound. Under that
Hoeffding design, zero observed damage needed 6,492 independent clean groups for
a 2% upper limit. The revised Stage-0 proposal asks an independent reviewer to
consider one all-gates-must-pass qualification claim at `alpha = 0.05`. Even
then, Hoeffding needs 59,915 applicable groups for a one-point paired margin at
zero observed difference, exceeding the existing evaluator's 5,000-case cap.
These are properties of those conservative bounds and proposed thresholds, not
evidence that those groups exist or that a different method will qualify G5.
[Maurer and Pontil's original paper](https://www.cs.mcgill.ca/~colt2009/papers/012.pdf)
states the Hoeffding comparison and develops a variance-sensitive alternative.

## Primary sources and transfer to Mos Eisley

| Source | Method supported | What must hold here |
|---|---|---|
| [Hoeffding, *JASA* 1963](https://doi.org/10.1080/01621459.1963.10500830) | Distribution-free concentration for sums of bounded variables; the current conservative baseline | Apply the exact bound to the registered independent-group units and their value ranges. It does not make correlated tasks independent or supply a prospective power calculation. |
| [Clopper and Pearson, *Biometrika* 1934](https://doi.org/10.1093/biomet/26.4.404) | Exact fixed-sample binomial confidence limits, including a one-sided rare-event upper limit | The gating observation must truly be an independent, identically distributed Bernoulli unit. It does **not** directly apply to arbitrary within-group average damage values, selective labels or repeated looks. Turning each group into a binary any-damage event changes the estimand unless that event was the registered target. |
| [Maurer and Pontil, COLT 2009, Theorems 4 and 11](https://www.cs.mcgill.ca/~colt2009/papers/012.pdf) | Finite-sample empirical-Bernstein bound for bounded independent values; the bound uses observed variance and an explicit remainder | Apply at the independent-group level, with the exact group estimand and sampling model reviewed. Low variance can narrow a bound, but missing labels, dependence and a selected or changing population still invalidate the transfer. Fixed-time use does not permit repeated favorable looks. |
| [Serfling, *Annals of Statistics* 1974](https://doi.org/10.1214/aos/1176342611) | Concentration for sampling without replacement from a finite population | If G5 samples groups from a fixed finite corpus without replacement, review this sampling regime before applying an independent-draw bound. It does not supply group IDs or resolve selective labeling. |
| [Newcombe, *Statistics in Medicine* 1998](https://www.eiti.uottawa.ca/~nat/Courses/csi5388/Newcombe.1998.pdf) | Confidence intervals for a difference between paired binary proportions; compares poor-coverage older methods with improved score/profile approaches | Useful only for independent pairs with one binary result per arm/pair and a registered paired-risk estimand. It does not automatically handle multi-task groups, correlated repetitions, incomplete pairs or all G5 gate types. Coverage at rare-event margins needs protocol-specific verification. |
| [Imai, King and Nall, *Statistical Science* 2009](https://doi.org/10.1214/08-STS274) and [Rabideau and Wang, *Biostatistics* 2021](https://doi.org/10.1093/biostatistics/kxaa007) | Design-based inference for cluster-randomized and matched-cluster experiments | Relevant to later live production comparisons, where one group receives one user-affecting policy. They do not justify duplicating writes or applying the frozen-start paired estimator to production traffic. Cluster definition, matching and allocation must precede outcomes. |
| [Howard et al., *Annals of Statistics* 2021](https://doi.org/10.1214/20-AOS1991) and [Lan and DeMets, *Biometrika* 1983](https://doi.org/10.1093/biomet/70.3.659) | Time-uniform confidence sequences and planned error spending for repeated looks | Candidates for separately reviewed continuous monitoring. They do not turn selected-action logs into counterfactual outcomes, recover missing probabilities, or fix label delay. Initial G5 can retain one fixed-horizon analysis. |
| [Horvitz and Thompson, *JASA* 1952](https://doi.org/10.1080/01621459.1952.10483446) and [ICH E9(R1), final guideline](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf) | Unequal-probability sampling estimation; advance definition of estimands, intercurrent events, missing data and sensitivity analyses | The ordinary audit and hard-case channels need known inclusion probabilities and separate reporting. Follow-up failure, cancellation and unresolved grades need a registered estimand and sensitivity analysis; neither source licenses filling missing values from outcomes. |
| [NIST Bonferroni method](https://itl.nist.gov/div898/handbook/prc/section4/prc473.htm) | Simultaneous error control across a fixed family of bounds | Use when making individually certified interval claims or multiple success-path claims; count those claims before allocating error. It is not automatically required within one conjunctive all-gates decision. |
| [FDA, *Multiple Endpoints in Clinical Trials*, 2022](https://www.fda.gov/media/162416/download) | With one all-endpoints-must-pass claim, co-primary endpoint tests do not inflate the overall false-success rate; multiple paths to success do | Transfer only to one precommitted conjunctive qualification claim. It does not give simultaneous interval coverage or free choice among candidate policies, benefit endpoints or later cohorts. |

## Illustrative arithmetic, not a sample-size commitment

At the proposed single-claim per-gate level `a = 0.05`, an exact one-sided
binomial upper limit after **zero** events would reach 2% at
`n = ceil(log(a)/log(0.98)) = 149` independent Bernoulli units. That is an
optimistic calculation for the *different* binomial design; Clopper–Pearson does
not validate the existing group-average estimand by itself.

For bounded independent group values in `[0,1]`, Maurer–Pontil Theorem 4's
one-sided empirical-Bernstein radius is
`sqrt(2 V_n log(2/a)/n) + 7 log(2/a)/(3(n-1))`. If every observed group value is
zero, its variance term is zero and the 2% upper radius is reached at `n = 432`.
For a paired difference in `[-1,1]`, applying the theorem to `(difference+1)/2`
and mapping back yields `n = 1,723` at a 1-percentage-point radius if every
observed paired difference is zero. These are **zero-variance benchmarks**, not
prospective power calculations. Any variation widens the bound, and the actual
group sampling, outcome missingness and multiplicity may demand more observations.
These calculations were recomputed directly from the published formula and the
proposal's `a`; they are inferences from the source, not numbers supplied by it.
They are not sample commitments for the revised claim.

## Recommendation for independent statistical review

First lock the sampling regime and target-population estimator. An unweighted
sample mean is unsuitable for a population-group mean under arbitrary unequal
inclusion probabilities; a finite frame sampled without replacement also needs
a design-matched interval. For independent identically distributed group draws,
review a fixed-horizon, group-level empirical-Bernstein replacement for Hoeffding.
It can preserve the equal-weight group estimand while using observed variance.
Assess the single-claim intersection-union decision separately from any individual
metric or multi-candidate claims. Keep the proposed safety thresholds; do not
select a method or benefit endpoint by looking at holdout outcomes. Then validate
coverage and decision behavior with deterministic fixtures and simulations covering rare harm,
heterogeneous group sizes, nonzero variance, incomplete pairs, missing follow-up,
all registered gates, multiple claim scopes and zero verified successes. Keep p95
latency descriptive unless a separate population-tail method is registered. Use only independent
development evidence for prospective variance and cost assumptions. Calculate
power, total assignments, price exposure and label workload before sealing.

If the source assumptions fail, use a conservative design-matched method or
redesign the population/estimand prospectively. Exact binomial and paired-binary
methods are useful alternatives only if the design truly produces their required
units. Continuous production cohorts additionally need the separate randomization
and time-uniform design in [plan §26.6](mos-eisley-plan.md#266-continuous-production-study-and-calibration).
No source here identifies the study's missing probabilities, groups, labels or
splits; no method is approved by this review alone.
