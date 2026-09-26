# G5 Stage-0 study manifest: source audit

Status: **pre-outcome source audit, 2026-09-26; manifest incomplete and unsealed**.
This records which sources can support the study-specific manifest in the
[G5 protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md) and
[Stage-0 gate proposal](G5_STAGE0_GATE_PROPOSAL.md). It grants no study,
qualification or production authority. The private local draft is
`private/g5/stage0-study-manifest.draft.json` and is ignored by Git. It contains
design metadata and explicit nulls, with no task content, outcomes or assignments.

| Manifest decision | Trusted source and what it establishes | Still needed |
|---|---|---|
| Family A arms, rubric outcomes and candidate safety/cost limits | The [G5 protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md) fixes the frozen-start paired comparison and outcome definitions; the [gate proposal](G5_STAGE0_GATE_PROPOSAL.md) records candidate numeric limits. | Exact arm, Stage-0 procedure, measurement route and rubric digests; owner and independent review of the candidate limits. The existing grading mechanism in [EVALUATION](EVALUATION.md#independent-grading-comparison) does not identify this study's rubric or graders. |
| Sampling regime and population estimator | [Horvitz and Thompson](https://doi.org/10.1080/01621459.1952.10483446) cover unequal-probability finite-population sampling; [Serfling](https://doi.org/10.1214/aos/1176342611) treats sampling without replacement; [Maurer and Pontil](https://www.cs.mcgill.ca/~colt2009/papers/012.pdf) give the independent-draw empirical-Bernstein option. These support method review after the design is known. | An approved task/group frame, target population, draw law or actual inclusion probabilities, stratum allocation, any needed joint probabilities, and a reviewer-approved estimator and interval. None may be reconstructed from sampled outcomes. |
| Independent groups, clean/defective labels and immutable splits | The [G5 protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md#population-pairing-and-assignment) specifies the rule and holdout isolation requirements. | Approved custodian-produced IDs, labels and split assignments, established before outcome access. Literature and sampling receipts cannot supply these values. This audit did not inspect any registry, custodian mapping, label store or outcome store. |
| Stage-0 benefit endpoint and `beta_min` | The [L5 project plan](adversarial-review-loop-project-plan.md#phase-l5--controlled-simplification-and-routing) describes Stage 0 as earlier defect prevention and calls for independently graded downstream defects and correct-work damage. [ICH E9(R1)](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf) supports defining the outcome, population and handling of intercurrent events before analysis. | One specific rubric outcome and a numeric minimum useful improvement chosen from approved independent development evidence and owner judgment, then frozen before holdout access. No general paper supplies a Mos Eisley-specific worthwhile effect size. |
| Fixed-horizon claim and feasibility | The [FDA's co-primary-endpoint guidance](https://www.fda.gov/media/162416/download) supports a single all-required statistical decision without a within-claim Bonferroni division; [Maurer and Pontil](https://www.cs.mcgill.ca/~colt2009/papers/012.pdf) support a bound only under its sampling assumptions. | Independent statistical review of the claim and method; prospective joint power and attainable-bound calculations using development assumptions; group counts, maximum assignments, price exposure and grading workload. The plan's 5,000-case and 50,000-assignment caps are capacity ceilings, not a feasible study design or spending authorization. |
| Eligible routes, cost cap and total budget | The [G5 protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md#decisions-and-comparisons) requires complete-policy accounting and pinned eligible routes. | Approved exact route/provider versions, current eligible conformance evidence, prices, common enforced task cap `B`, total study spending ceiling and an owner authorized to incur it. A provider price list alone would not authorize a route or budget. |
| Independent grading and statistical reviewer | The [G5 protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md#independent-outcomes-and-denominators) requires two authenticated, route-blind graders, a disjoint resolver and independent evidence review; [ADJUDICATION_AUTHENTICATION](ADJUDICATION_AUTHENTICATION.md) documents an existing signature mechanism. | Named study owner, two grader identities/keys, disjoint resolver, independent statistical reviewer, their signed review and authority separation. No document names them for this study. |
| External pre-outcome seal | [RFC 3161](https://www.rfc-editor.org/info/rfc3161/) defines a third-party signed timestamp over a digest; [Sigstore Rekor](https://docs.sigstore.dev/logging/overview/) documents an independently verifiable append-only transparency log. | Select and approve an independent operator/location, reveal only the exact manifest digest and permitted safe metadata, verify the timestamp/inclusion proof, retain the receipt, and confirm it predates assignment and outcome access. A local Git commit or hash alone does not provide this timing evidence. |

## Completion boundary

The private draft intentionally leaves every absent study-specific value null.
Its candidate gates and document hashes are traceable, but no sampling frame,
probabilities, group IDs, labels, split assignments or outcomes were inferred.
Do not calculate sample size or seal the draft until the approved frame and
independent development assumptions exist. If the resulting design cannot meet
every gate within its authorized spend and group capacity, revise the design
prospectively and obtain a new review before any assignment.
