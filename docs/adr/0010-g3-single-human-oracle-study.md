# ADR-0010: Narrow G3 objective-oracle study with one human

- Status: accepted planning direction; source, method, and cohort not sealed
- Date and owner: 2026-09-27, Joshua Myers

## Context and options

Joshua Myers is the only human available for the proposed G3 study. The current
`IndependentLabelCatalog` requires two distinct enrolled grader identities and
keys, and the current policy seal requires a random ordinary-task audit in both
splits. Distinct keys do not establish independent human judgment or ground truth.
[ADR-0008](0008-g3-owner-statistical-review.md) permits Joshua to conduct the
statistical-method review, but does not change these label or sampling rules.

The owner approved a **narrow objective-oracle study** as the single-human
planning direction. The options were to wait for independent human graders, run
an owner-operated descriptive pilot, or prospectively design a separate study
whose eligible cases have a reproducible external ground-truth oracle.

## Decision and consequences

Design a separate, prospective comparison limited to tasks with a pinned,
independently reproducible objective oracle. Joshua is the sole human owner and
may operate the study and conduct the disclosed owner statistical review. The
protocol must define eligible case types, source rights and version, exact oracle,
grader/operator and key custody, independence groups, sampling probabilities,
calibration, disagreement handling, holdout controls, harm limits, inference,
resource ceilings, and the maximum claim before outcomes are accessible.

An automated oracle may establish a narrow task fact when its inputs and expected
behavior are independently checked. A second signature under Joshua's control
must never be called an independent human grade. The current two-grader catalog
and ordinary-audit seal cannot be used for this variance without an explicit
schema/governance amendment and negative tests. Do not relabel synthetic benchmark
cases as ordinary tasks or silently omit the ordinary-audit requirement. The
study's possible claim is performance on its defined oracle-verifiable frame;
it does not satisfy the original broad G3 ordinary-task qualification or any G5/G6
promotion gate by itself.
Joshua's later [real production outcome direction](../PRODUCTION_OUTCOME_ACCEPTANCE.md)
also limits this oracle study to preproduction calibration or its explicitly
source-bound claim. A public case replay, even if executed on production
infrastructure, is not an observed outcome of a real owner task and cannot enter
a production completion, harm or savings denominator.

NIST's [Juliet C/C++ 1.3 suite](https://samate.nist.gov/SARD/test-suites/112)
was subsequently authorized for a [source audit](../G3_JULIET_SOURCE_AUDIT.md),
not enrolled as a study source. The archive checksum matched NIST's listing, but
the audit found label cues, related variants, absent observable failures and
known source defects. Juliet can be considered only for a separately validated
narrow flaw-detection subset. No case is labeled or assigned to a holdout by this
ADR. The prior candidate's 400 groups per class and exact-binomial gates cannot
be carried over without a qualified source and appropriate sampling model.

A later [case-source assessment](../G3_ORACLE_CASE_SOURCE_QUALIFICATION.md)
reproduced one SWE-rebench V2 Go task's fail-before/pass-after test result in a
pinned, network-disabled image. The full source was not admitted: a complete
eligible inventory, safe task projection, oracle controls and reviewed grouping
remain open. The assessment did not amend this decision or enroll a case.

The proposed harm margins, $200,000 planning ceiling, and six arm names in the
owner review package remain proposals. This decision grants no spending, provider
execution, signed-label issuance, empirical registration, qualification, or live
routing authority. Reversal is possible before a cohort is registered; after
registration, a changed design needs a new prospective version and fresh holdout.

## Verification

Before any empirical seal, verify a named authorized source and immutable case
inventory or generation recipe; independently reproduce oracle results on
predeclared controls; establish source-family grouping and known selection/label
observation probabilities; reproduce the revised feasibility and inference
calculation; review exact arm implementations and costs; test the new verifier's
failure cases; and obtain Joshua's signed, outcome-blind disposition. Register the
exact protocol externally before assignments or outcome inspection. Report source
and operator limits in every result. Reconsider this decision if the oracle cannot
establish the claimed task fact or the eligible independent case pool is too small.

Current evidence and limits: [G3 context-study guide](../G3_CONTEXT_STUDY.md),
[G3 label threat model](../G3_LABEL_INVENTORY_THREAT_MODEL.md),
[project plan §26.4](../mos-eisley-plan.md#264-delivery-order-and-accountable-gates),
and [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
on calibrating automated grading against human judgments.
