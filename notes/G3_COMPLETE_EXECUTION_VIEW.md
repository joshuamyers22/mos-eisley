# Work note: four G3 public-case execution views

- Status: closed for this four-case audit; source admission open
- Owner: Joshua Myers for source and method disposition
- Started/last updated: 2026-09-28 UTC
- Review by: next G3 source/method review
- Related decision: [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md)

## Objective and completion evidence

- Intended outcome: qualify or reject the **complete offline execution view** for each of the four frozen public candidates, including a pinned base tree, issue-only task packet, isolated container workspace and independent whole-suite controls.
- Invariants: no sampling registry, custodian mapping, label store or outcome store access; no inferred probabilities, groups, labels or splits; no model/provider/arm execution, eligible cohort, or production claim; operator diffs and raw logs stay out of task packets and sampling artifacts.
- Completion evidence: [audit and decision](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md), [verification](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_VERIFICATION.md), [threat model](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_THREAT_MODEL.md) and two reproducible tools.
- Risk: high source integrity, rights, model leakage and false oracle claims. Joshua's accountable review remains necessary.
- Resource ceiling and stop: four pinned public source archives, one candidate image at a time, network-disabled controls at 2 CPUs/2 GiB/256 PIDs with 360-second run timeout, zero provider spend. Stop each failed oracle; repeat a passing case three rounds for stability; do not enlarge the candidate frame in this pass.
- Guides/templates selected: [Python engineering](../docs/PYTHON_ENGINEERING_GUIDE.md), [bounded verification](../docs/AGENTIC_VERIFICATION_GUIDE.md), [verification loop](../templates/AGENTIC_VERIFICATION_LOOP.md), [threat model](../templates/THREAT_MODEL.md), [work note](../templates/WORK_NOTE.md).

## Context retrieved

[Project brief](../PROJECT_BRIEF.md), [memory](../PROJECT_MEMORY.md), [plan](../docs/mos-eisley-plan.md), [candidate frame](../docs/G3_SWE_REBENCH_CANDIDATE_FRAME.md), [full-source audit](../docs/G3_SWE_REBENCH_FULL_SOURCE_AUDIT.md), [single-human ADR](../docs/adr/0010-g3-single-human-oracle-study.md), and [production-outcome contract](../docs/PRODUCTION_OUTCOME_ACCEPTANCE.md).

## Observations and actions

| UTC date | Type | Result | Evidence |
|---|---|---|---|
| 2026-09-28 | source verification | Four exact Git commit/root-tree/archive sets authenticated; 1,428 blobs verified; filtered workspaces contain 711 fewer files, including policy-bot vendor and PEM-bearing example config and revive encrypted key. | [Workspace verifier](../tools/g3_execution_view_audit.py), [audit](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md) |
| 2026-09-28 | negative check | Mutating a Git directory entry initially escaped a blob-only check; full tree reconstruction was added and the mutation was rejected. | [Verification](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_VERIFICATION.md) |
| 2026-09-28 | setup correction | Carapace's first container had non-executable `/tmp`; its failed launch logs were separated, and the valid round used executable temporary build space. | [Verification](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_VERIFICATION.md) |
| 2026-09-28 | oracle result | Policy-bot passed three fresh offline base/gold/wrong whole-suite rounds and parser fault checks. Its duplicate P2P name was handled by a disclosed all-occurrences rule, frozen before rounds two and three. | [Audit](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md), [control tool](../tools/g3_oracle_controls.py) |
| 2026-09-28 | oracle result | Carapace, osv-scanner and revive failed their exact offline whole-suite controls; no source labels or cohorts were created. | [Audit](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md) |
| 2026-09-28 | interruption recovery | An interrupted first attempt at policy-bot round three left only a partial workspace/cache; it was preserved separately and the full round was rerun fresh. | [Verification](../docs/G3_SWE_REBENCH_EXECUTION_VIEW_VERIFICATION.md) |

## Handoff and close

- Current state: one bounded preproduction execution view passes; three fail. The four IDs remain historical source candidates, **zero enrolled G3 cases**.
- Next smallest safe action: Joshua's outcome-blind rights/source/oracle disposition for policy-bot and a new prospectively bounded candidate pool with defensible dependence and six-arm spend/sample feasibility. The single-human verifier amendment is still required before registration or assignment.
- Checks: pinned view rebuild, altered-tree rejection, Ruff, casewise offline controls and parser mutations. Full repository quality gate is recorded in the verification file.
- Temporary artifacts: authenticated public archives and raw control logs retained under `/private/tmp/g3_execution_view_20260928` for owner review, outside Git and sampling stores. Four newly pulled case images were removed after controls. No private evaluation store was accessed.
- Durable fact promoted: `delivery.g3.feasibility` in [project memory](../PROJECT_MEMORY.md); [roadmap](../docs/ROADMAP.md) and [plan](../docs/mos-eisley-plan.md) updated. No ADR or source admission decision was made by this audit.
