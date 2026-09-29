# Work Note: G3 single-human objective-oracle direction

- Status: closed for planning record; empirical design remains open
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Last updated (UTC): 2026-09-27
- Review or delete by: next G3 source and method review
- Related decision: [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md)

## Objective and completion evidence

- Intended outcome: record the owner's approval of a narrow prospective study with Joshua as the only human.
- Required invariants: no fabricated labels/signatures; no silent bypass of two-grader or ordinary-audit rules; no restricted sampling/label/outcome-store access; no execution or spend authority.
- Evidence of completion: ADR, plan, roadmap, G3 guide and review package agree on scope and open gates.

## Context retrieved

[Project brief](../PROJECT_BRIEF.md), [plan](../docs/mos-eisley-plan.md),
[G3 guide](../docs/G3_CONTEXT_STUDY.md), [threat model](../docs/G3_LABEL_INVENTORY_THREAT_MODEL.md),
[ADR-0008](../docs/adr/0008-g3-owner-statistical-review.md),
[context-study schema](../src/mos_eisley/evaluation/context_study.py), and
the production-template [ADR](../templates/ADR.md), [work-note](../templates/WORK_NOTE.md)
and [verification](../templates/AGENTIC_VERIFICATION_LOOP.md) templates.

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-27 | decision | Joshua approved a narrow objective-oracle G3 study with him as only human; no source named. | Owner direction recorded in [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md) | Audit and select source. |
| 2026-09-27 | observation | Existing verifier requires two distinct signed graders and ordinary-task audits in both splits. | [G3 guide](../docs/G3_CONTEXT_STUDY.md) | Amend protocol and verifier prospectively. |
| 2026-09-27 | observation | Joshua authorized a NIST Juliet source audit; archive checksum matched the published digest. Related cases, answer cues and oracle limits block enrollment. | [Juliet audit](../docs/G3_JULIET_SOURCE_AUDIT.md) | Qualify a narrow subset or keep the source descriptive. |

## Handoff

- Current state: approved planning direction recorded; proposed harm/spend/arm identifiers remain unapproved; no source, labels or cohort sealed.
- Next smallest safe action: validate a leakage-resistant Juliet subset with reproducible oracle controls and reviewed source-family groups, or choose another source.
- Blocker and required authority/input: qualified oracle subset plus accountable statistical/spend review and actual case/arm/cost evidence.
- Checks already run: see [verification record](../docs/G3_SINGLE_HUMAN_ORACLE_STUDY_VERIFICATION.md).

## Close and promote

- Outcome and verification: planning decision documented; empirical work pending.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.g3.feasibility`.
- Decision promoted to ADR/documentation: ADR-0010, G3 guide, plan and roadmap.
- Regression test, issue, or improvement-plan link: verifier/schema amendment remains future work under ADR-0010.
- Temporary artifacts removed: none.
