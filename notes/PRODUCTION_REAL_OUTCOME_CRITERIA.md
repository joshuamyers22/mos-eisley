# Work Note: Real outcomes for production evaluation

- Status: complete
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Last updated (UTC): 2026-09-27
- Review or delete by: next production-study protocol review
- Related decision: [ADR-0009](../docs/adr/0009-continuous-production-evaluation.md)

## Objective and completion evidence

- Intended outcome: make real outcomes of actual owner-authorized tasks the binding acceptance criteria for production evaluation and optimization after applicable launch gates.
- Invariants: existing G2–G6 entry gates, owner isolation, independent grading requirements, unknown/missing outcomes, protected prospective assignment and spending limits remain in force. No sampling registry, mapping, label store or outcome store is accessed, and no probability, group, split or label is inferred.
- Non-goals: activate a live cohort, choose numeric thresholds, alter the existing offline verifier, or present a benchmark case as a production task.
- Evidence of completion: plan, ADRs, G3/G5 guides, roadmap and memory agree on the real-outcome contract and its still-open implementation/approval gates.
- Risk/resource bound: high-risk governance and private production data; documentation only, zero provider or study spend, one combined repository gate before publication.

## Context retrieved and selected guidance

[README](../README.md), [brief](../PROJECT_BRIEF.md), [plan §26.6](../docs/mos-eisley-plan.md#266-continuous-production-study-and-calibration),
[ADR-0009](../docs/adr/0009-continuous-production-evaluation.md),
[ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md),
[G3 guide](../docs/G3_CONTEXT_STUDY.md), [G5 protocol](../docs/G5_WHOLE_TASK_STUDY_PREREGISTRATION.md),
[source assessment](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION.md),
[production-template ADR](../templates/ADR.md), [work-note](../templates/WORK_NOTE.md),
[verification](../templates/AGENTIC_VERIFICATION_LOOP.md), and
[threat-model](../templates/THREAT_MODEL.md) templates. The selected threat-model
elements are embedded in the [outcome contract](../docs/PRODUCTION_OUTCOME_ACCEPTANCE.md#trust-boundary-and-verification).

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-27 | observation | Plan §26.6 already requires live ordinary tasks, independent grading and follow-up, but it does not state a binding real-outcome acceptance definition distinct from benchmark and proxy evidence. | [Plan](../docs/mos-eisley-plan.md#266-continuous-production-study-and-calibration), [ADR-0009](../docs/adr/0009-continuous-production-evaluation.md) | Make outcome and denominator rules explicit. |
| 2026-09-27 | decision | Joshua directed production test criteria to be real outcomes. Public oracle cases remain preproduction source-bound evidence. | [Outcome contract](../docs/PRODUCTION_OUTCOME_ACCEPTANCE.md), [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md) | Verify cross-document status and local links. |
| 2026-09-27 | verification | Local relative links and staged whitespace check passed. `make check` passed: Ruff, Pyright, 2,540 source-tree tests (4 skipped), 88% coverage, export verification, wheel build and 1,894 installed-wheel smoke tests. | [Verification record](../docs/PRODUCTION_OUTCOME_ACCEPTANCE_VERIFICATION.md) | Publish on the open PR. |

## Handoff

- Current state: documentation criterion and verification complete; publication on PR #241 follows this work note.
- Next smallest safe action: later study owner prepares a prospective cohort manifest with real task evidence and approved numerical gates.
- Blocker and required authority/input: actual owner-authorized traffic, approved outcome thresholds/follow-up, grader or objective-outcome custody, and a prospective cohort manifest are still needed before a production claim.
- Checks already run: initial source/plan/ADR read, local links and staged diff, full `make check`; no production data accessed.

## Close and promote

- Outcome and verification: real-outcome criterion recorded and cross-referenced; full repository gate passed. No production cohort was sampled or scored.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.continuous-production-plan`.
- Decision promoted to ADR/documentation: ADR-0009, plan §26.6, production outcome contract.
- Regression test, issue, or improvement-plan link: no code change; prospective cohort implementation remains under §26.6.
- Temporary artifacts removed: none.
