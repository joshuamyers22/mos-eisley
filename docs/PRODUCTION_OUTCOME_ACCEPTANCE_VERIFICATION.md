# Agentic Verification Loop: Real production outcomes

## Objective and authority

- Requirement: Joshua directs production test and optimization acceptance to use real outcomes.
- User journey: a reviewer can tell which observed task results govern a production decision and why a green benchmark/test cannot substitute for them.
- Invariants: no private sampling/label/outcome-store access; no inferred groups, probabilities, labels or splits; no new production traffic, spend, policy promotion or numerical thresholds.
- Risk class: high-risk statistical governance and private production evidence.
- Implementation owner: Codex for documentation; Joshua Myers for the accepted direction and later accountable protocol approval.
- Starting revision/worktree: `fb26807d49379b698d17c4f6cf9b6bc6079a1e70`, clean.
- Selected guidance: [bounded verification guide](AGENTIC_VERIFICATION_GUIDE.md), [work-note](../templates/WORK_NOTE.md), [verification](../templates/AGENTIC_VERIFICATION_LOOP.md) and [threat-model](../templates/THREAT_MODEL.md) templates; trust-boundary findings are in the [outcome contract](PRODUCTION_OUTCOME_ACCEPTANCE.md#trust-boundary-and-verification).

## Rubric

| Dimension | Severity | Evidence | Pass threshold |
|---|---|---|---|
| Real production outcome | Blocking | Contract and §26.6 | Actual owner-authorized tasks, mature verified outcomes and all-assigned denominators govern production acceptance |
| Proxy separation | Blocking | G3 source assessment, ADR-0010 and G5 protocol | Public or synthetic cases, test passes and model judges cannot become production outcomes by relabeling |
| Statistical and grade truth | Blocking | ADR-0009, plan, contract | Unknown labels/follow-up remain unknown; no single-human judgment presented as independent grading; no thresholds invented |
| Authorization and privacy | Blocking | Plan and threat boundary | No live study authority, restricted-store access or cross-owner pooling added |
| Documentation integrity | Material | Links, diff and repository gate | All changed documents agree and checks pass |

## Budget and stopping rules

- Two evidence-changing passes: current plan/ADR/source gap analysis, then cross-document contract review.
- Zero provider or production-study spend; one repository `make check` for the combined documentation batch.
- Stop when the direction is explicit and linked but cohort-specific thresholds and evidence remain correctly open; do not manufacture a real result or independent grader.

## Iterations

| # | Implemented slice | New evidence/context | Finding | Decision and correction | Gates |
|---:|---|---|---|---|---|
| 1 | Production outcome contract and §26.6 criterion | Existing plan already has live tasks and delayed follow-up; primary research warns against treating surrogate outcomes as the decision target | Acceptance target and all-assigned denominators were implicit | Define real completion, defect, damage, harm, cost, latency and unknown states | Local links and staged diff pass |
| 2 | ADR/G3/G5/roadmap/memory alignment | Prior oracle study and public-source screening are source-bound, while G5 frozen-start is preproduction | Could otherwise be mistaken for production proof | Explicitly limit these claims and preserve all existing live-cohort gates | `make check` passed |

## Exit

- Stop reason: documentation criterion is explicit and verified; prospective cohort inputs remain open.
- Rubric result: all five documentation dimensions pass. No empirical production result is claimed.
- Full quality gate: `make check` passed on 2026-09-27: Ruff, Pyright, 2,540 source-tree tests (4 skipped), 88% coverage, export verification, wheel build, and 1,894 installed-wheel smoke tests (OK). Local relative links and `git diff --cached --check` passed.
- Human/domain approval: Joshua provided the real-outcome direction; no cohort-specific threshold, label, sample or release approval is inferred.
- Remaining uncertainty: actual product readiness, owner-authorized tasks, independent or objective outcome ascertainment, feasible cohort/sample and spend, numeric safety and benefit thresholds, and external pre-outcome registration.
- Durable facts: plan §26.6, ADR-0009, outcome contract and project memory.
