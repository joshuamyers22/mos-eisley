# Production evaluation: real-outcome acceptance contract

- Status: accepted owner direction for planning; no production cohort or metric threshold is sealed.
- Owner: Joshua Myers
- Date: 2026-09-27

Joshua's [2026-09-28 timing decision](adr/0011-defer-studies-until-production.md)
requires Mos Eisley to be in production before any study is executed. This
contract defines later outcome acceptance; it does not admit a prelaunch cohort.

## Scope and decision

Once the product has met its applicable launch gates, the acceptance criteria for
production evaluation and optimization are **observed outcomes of real,
owner-authorized tasks**. Each task remains in its assigned policy's denominator
from admission through a frozen follow-up window, including failures, cancellations
and unresolved work. The [continuous production plan](mos-eisley-plan.md#266-continuous-production-study-and-calibration)
governs collection, randomized comparisons and later promotion. This document
specifies what a production outcome must mean before any numerical threshold or
study cohort is approved.

Offline unit tests, NIST Juliet, SWE-rebench cases, seeded defects, passing
repository tests, model-judge verdicts, and task-cost estimates can exercise the
product or calibrate measurement. They do not supply a production success,
harm, or savings observation. The single-human oracle proposal in
[ADR-0010](adr/0010-g3-single-human-oracle-study.md) remains unexecuted until
production and, if later admitted, has only a narrow source claim rather than
production qualification. Research on online
experiments also finds that surrogate metrics can lead to different launch
decisions from the delayed outcome they approximate; this contract therefore
keeps the real outcome as the decision target
([Duan, Ba and Zhang, 2021](https://arxiv.org/abs/2106.01421)).
An experimental study of human-AI work likewise found that proxy tasks could
misrepresent performance on the actual task
([Buçinca et al., 2020](https://arxiv.org/abs/2001.08298)).

## Evidence required for each admitted task

The pre-outcome cohort manifest fixes the owner, ordinary-task eligibility,
requested result and source-state reference, treatment policy, group/split,
assignment probability, follow-up deadline, outcome rubric, evidence sources,
grader/resolver custody, missingness rule, and allowable data access. Admission
and assignment are durable before user-affecting work. An absent probability,
group, split, label or follow-up is **unknown**; it is never inferred from
subsequent activity. A sampling receipt remains metadata and grants no access
to private mappings or outcomes.

| Real outcome | Task-level decision evidence | Denominator and failure handling |
|---|---|---|
| Verified completion | The requested work reaches a current final disposition, checked against the original requirements and actual repository or operational state. Independent review uses the final artifact, relevant verification, and owner disposition where applicable. | All assigned tasks. Timeout, abandonment, cancellation, failed verification and unfulfilled requests remain noncompletion. Owner acceptance or a green test alone is insufficient to establish correctness. |
| Escaped defect and missed evidence | A defect or material missed requirement is confirmed from subsequent actual use, review, issue/reopen, incident, or follow-up inspection and linked to the assigned task under the frozen rubric. | All assigned tasks. Report status at the registered follow-up deadline and missing follow-up separately; silence is not proof of no defect. |
| Correct-work damage | An independently adjudicated unnecessary requested change or an introduced regression on work established acceptable at admission. | All assigned initially acceptable tasks; the pre-task acceptable status must be known before outcome review. |
| Harmful action | A confirmed unauthorized or unsafe write, credential/data exposure, policy violation, destructive action, or other registered harm during the actual task. Safety stops and their assigned tasks remain in the record. | All assigned tasks; an unverified allegation remains unresolved, not silently clean. |
| Whole-task resources | Actual settled plus conservatively retained uncertain spend, and assignment-to-final-disposition elapsed time, including planning, children, reviews, retries, failed/abandoned work and follow-up costs as specified in the manifest. | All assigned tasks, including zero-success tasks. No success-only cost or latency claim. |

An outcome may be supported by machine-verifiable operational evidence, but its
meaning and linkage to the user's request must follow the frozen rubric. Human
judgment remains necessary for ambiguous correctness, missed evidence and harm.
With Joshua as the only available human, an owner-only judgment is disclosed as
such; it does not satisfy the current two-independent-grader catalog or establish
an independent quality label. A future objective-outcome variance must be
specified and validated prospectively. Unknown or disputed outcomes remain
visible, and a favorable result requires the registered sensitivity analysis to
pass despite them.
Until qualified independent grading or a reviewed objective production-outcome
variance exists, an owner-only record can support descriptive monitoring but
cannot pass a quality or harm promotion gate.

## Production decision rules

1. **Measurement:** Level 1 reports real task outcomes and ascertainment under
   the deployed fixed policy. It may trigger safety stop or quarantine; it does
   not estimate the effect of an unassigned alternative.
2. **Comparison:** Level 2 assigns one already-qualified, complete, user-affecting
   policy per real task or independent group under a precommitted owner-scoped
   randomized design. Analyze all assignments by intent to treat after follow-up
   matures. A shadow run is diagnostic and does not stand in for the unobserved
   production counterfactual.
3. **Optimization:** Level 3 freezes each candidate from permitted prior-window
   evidence, tests it on a fresh later cohort with real outcomes, and requires
   reviewed quality/harm, completion, whole-task savings, latency, error-budget
   and rollback gates before promotion. Early safety stops cannot count as
   successful efficacy results. Underpowered or incomplete cohorts remain
   inconclusive.

The exact outcome definitions, baseline, absolute harm ceilings, non-inferiority
margins, useful cost saving, latency ceiling, follow-up window, sample size,
spend cap and simultaneous error allocation are **open manifest inputs**. They
must be approved and externally timestamped before assignment or outcome access.
No threshold is supplied by this document. A favorable proxy or cheaper run
cannot replace a failed, missing or inconclusive real-outcome gate.

## Trust boundary and verification

Production tasks, private outcomes and owner identities are sensitive assets;
assignment and grade integrity are decision-critical. Threats include selective
recording of successes, missing follow-up treated as clean, retroactive group or
probability repair, arm-aware grading, copied holdout material, proxy substitution,
unauthorized data transfer, and promotion from a broken monitor. Controls are
owner-scoped access, frozen task/rubric and assignment records, blinded qualified
grading where the outcome requires it, durable before-send links, complete cost
reconciliation, explicit unknown states, once-used cohort decisions, and stop/
rollback on missing evidence. The [G3 label threat model](G3_LABEL_INVENTORY_THREAT_MODEL.md)
and [§26.6 verification matrix](mos-eisley-plan.md#266-continuous-production-study-and-calibration)
remain applicable.

Before any production acceptance claim, replay the exact registered outcome
classification on a controlled audit set and exercise missing follow-up,
noncompletion, reopens, regression, harmful action, uncertain spend, assignment
loss and grader disagreement. Then inspect a mature real cohort against its
pre-outcome manifest. Fixture passes establish the measurement mechanism only;
the real cohort supplies the product-outcome evidence. No production cohort was
read, created, assigned or scored for this planning decision.
