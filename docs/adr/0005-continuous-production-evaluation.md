# ADR 0005: Continuous owner-scoped production evaluation

Date: 2026-09-25. Status: accepted plan direction; implementation and production
authorization pending. The controlling requirements are
[plan §26.6](../mos-eisley-plan.md#266-continuous-production-study-and-calibration).

## Context

The initial G5 design compares complete workflows from separate frozen starts and
uses a once-used holdout. That establishes a finite qualification path but does
not by itself measure changing production traffic or support later calibration.
The existing routing design permits a bounded production cohort only after G5/G6
and allows monitoring to stop traffic. It does not authorize continued learning
or repeated testing against the same holdout. Mos Eisley's §17 ownership contract
prohibits pooling even anonymized evidence across users.

The production project template calls for decision-linked telemetry, independent
evidence, bounded verification, immutable releases and exercised rollback. These
principles guide the new production study contract; the template is not a source
of sampling assignments, numerical thresholds or runtime authority.

## Decision

1. Use the **same pinned independent grading rubric** for passive production
   measurement, bounded live comparisons and recurring calibration. Production
   model-judge verdicts remain proxy observations. A rubric change needs a new
   reviewed lineage and bridge study; old and new grades are not silently pooled.
2. Collect owner-scoped, versioned decision and outcome evidence under the
   deployed fixed policy first. Require a reviewed ordinary-task audit and delayed
   independent follow-up. Monitoring may stop or quarantine, not promote.
3. Compare only already-qualified complete policies in a registered, bounded
   production cohort. Assign one user-affecting policy per task/group; do not
   replay writes to create paired observations. Use a reviewed randomized
   whole-task estimator, not the offline fixed-matrix scorer or proxy outcomes.
4. Recalibrate repeatedly from mature prior-window evidence, freeze a candidate,
   qualify its exact policy, and test it on a fresh future cohort. Keep policy
   versions immutable during a cohort. Every deployment requires a new independent
   promotion/control decision, one-use dispatch and rollback readiness. No
   per-request self-modification is authorized. Within-cohort adaptation requires
   a further G7/R4 protocol.
5. Reserve a family-wide inference/error budget across repeated cohort decisions.
   Each cohort has a pre-outcome, externally retained manifest and once-used
   holdout. Safety stops may occur at any time; early favorable observations do
   not qualify a candidate. Missing probabilities, groups, labels, splits or
   follow-up remain unknown and cannot be reconstructed from outcomes.

## Consequences

- G2/G4 enable the applicable live workflow; G5 qualifies any user-affecting
  candidate; G6 governs production dispatch and each promotion. The three levels
  in §26.6 are additional gates, not evidence that those earlier gates passed.
- Production evidence and derived policies belong to one owner. Owner reset or
  deletion invalidates dependent decisions. No product-wide model policy is
  learned from pooled private user tasks.
- Continuous evidence requires durable before-send assignment records, safe
  operational telemetry, independent grading capacity, explicit follow-up and
  retention, an error-budget ledger, target-host failure tests, and an on-call
  stop/rollback path. A quiet dashboard does not authorize reactivation.
- Underpowered owner-specific traffic, unknown inclusion, inadequate label
  follow-up, or an infeasible spend/sample design yields an inconclusive result.
  Full review and fixed eligible routes remain available.
- The initial [G5 preregistration protocol](../G5_WHOLE_TASK_STUDY_PREREGISTRATION.md)
  remains unsealed until its study-specific inputs are supplied. This ADR neither
  fills those inputs nor activates any production experiment.

## Alternatives considered

- Reusing one historical holdout for every recalibration would make later
  decisions dependent on repeatedly inspected evidence; reject it.
- Updating the production policy automatically from operational metrics would
  substitute proxy outcomes for independent grades and bypass promotion; reject it.
- Running every experimental arm on a live task would duplicate user-visible
  effects and approvals; use one assignment and isolated shadow work where
  permitted.
- Pooling anonymized users to improve sample size conflicts with §17 ownership;
  retain owner-specific analyses and report infeasibility when applicable.

## Review and verification

Before enabling any level, assign an implementing owner and independent evidence
reviewer; freeze its rubric, acceptance thresholds, resource ceiling and stop
rules. Verify owner isolation, decision/event durability, study admission,
randomization, missingness, delayed outcomes, failed/abandoned-task accounting,
drift, spending, monitor outage and rollback with fixtures and production-like
fault injection. Review later windows against the registered baseline and retain
unresolved findings. The roadmap reports each level's actual maturity separately.
