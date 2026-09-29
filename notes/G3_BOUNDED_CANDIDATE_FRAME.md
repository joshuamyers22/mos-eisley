# Work Note: G3 bounded candidate frame

- Status: closed for row-projection slice; source enrollment open
- Owner: Joshua Myers
- Started/last updated (UTC): 2026-09-28
- Review by: G3 source/method disposition
- Related decision: [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md)

## Objective and completion evidence

- Intended outcome: a bounded, reproducible public source screen and model-visible issue-only packets for review.
- Invariants: no project sampling/custodian/label/outcome store access; no inferred probabilities, groups, labels or splits; no arm/provider dispatch or production claim; no task text in source-frame metadata.
- Completion evidence: pinned Parquet rebuild; four packet allowlists and checksums; original issue equality and base-license checks; negative source/packet mutation; repository gate.
- Risk class: material source integrity, rights and future evaluation leakage.
- Resource ceiling: existing 429 MB public source; no new image pulls, zero provider/study spend, no case execution.
- Selected guides/templates: [Python guide](../docs/PYTHON_ENGINEERING_GUIDE.md), [bounded verification guide](../docs/AGENTIC_VERIFICATION_GUIDE.md), [verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), [work note](../templates/WORK_NOTE.md), [threat model](../templates/THREAT_MODEL.md).

## Context retrieved

[Project brief](../PROJECT_BRIEF.md), [memory](../PROJECT_MEMORY.md),
[plan](../docs/mos-eisley-plan.md), [full-source audit](../docs/G3_SWE_REBENCH_FULL_SOURCE_AUDIT.md),
[single-human ADR](../docs/adr/0010-g3-single-human-oracle-study.md),
and [production outcome contract](../docs/PRODUCTION_OUTCOME_ACCEPTANCE.md).

## Observations and actions

| UTC date | Type | Result | Evidence |
|---|---|---|---|
| 2026-09-28 | observation | Exact bounded Go screen returned 453 rows in 107 repository names; deterministic breadth cap identified 12 issue-text inspection rows. | [Rebuild tool](../tools/g3_candidate_task_views.py), [frame](../docs/G3_SWE_REBENCH_CANDIDATE_FRAME.json) |
| 2026-09-28 | observation | Four issue statements exactly matched their original GitHub issue title/body, and exact base-commit license files had Apache-2.0 or MIT headers. Eight other rows were deferred with reasons. | [Frame review](../docs/G3_SWE_REBENCH_CANDIDATE_FRAME.md) |
| 2026-09-28 | artifact | Four opaque JSON task packets contain only schema version and original issue text. Operator-only frame has IDs, base commits, license references and packet hashes, with no task text. | [Task packets](../docs/g3_candidate_task_views_v1/packet-001.json), [frame](../docs/G3_SWE_REBENCH_CANDIDATE_FRAME.json) |
| 2026-09-28 | verification | Pinned rebuild passed; wrong source and tampered packet were rejected; restored packet passed. | [Verification](../docs/G3_SWE_REBENCH_CANDIDATE_FRAME_VERIFICATION.md) |
| 2026-09-28 | verification | Host-permitted source gate passed 2,540 tests; first wheel smoke found one intermittent observer exchange error, six focused installed-wheel repetitions passed, and complete wheel smoke rerun passed 1,894 tests. | [Verification](../docs/G3_SWE_REBENCH_CANDIDATE_FRAME_VERIFICATION.md) |

## Handoff

- Current state: row-derived task projection frozen for four source candidates. No eligible study frame or full execution view exists.
- Next smallest safe action: inspect exact base snapshots for answer disclosure and run predeclared base/gold/wrong/ambiguous oracle controls on the four candidates under offline resource limits.
- Blocker/authority: Joshua must later review rights, dependence, six-arm feasibility and the single-human method amendment before any source/cohort disposition.
- Checks run: recorded in the linked verification file; no private evaluation stores accessed.

## Close and promote

- Outcome: four source-screen packets, zero enrolled G3 cases.
- Durable fact: updated `delivery.g3.feasibility` in [project memory](../PROJECT_MEMORY.md).
- Decision: [candidate frame](../docs/G3_SWE_REBENCH_CANDIDATE_FRAME.md) records scoped status; ADR-0010 remains planning only.
- Temporary artifacts: existing public Parquet and earlier raw control logs remain outside Git for source review.
