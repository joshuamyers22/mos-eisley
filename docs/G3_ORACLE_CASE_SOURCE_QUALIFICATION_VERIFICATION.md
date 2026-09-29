# Agentic Verification Loop: G3 oracle case-source assessment

## Objective and authority

- Requirement: user requested qualification of an oracle-backed case source under [ADR-0010](adr/0010-g3-single-human-oracle-study.md).
- Outcome: an accountable reviewer can distinguish a reproduced one-case oracle from a source eligible for prospective G3 enrollment.
- Invariants: no restricted project sampling/label/outcome access; no inferred probabilities, groups, labels or splits; no fabricated signatures or spend authority.
- Non-goal: executing study arms or sealing a cohort.
- Risk class: high-risk statistical governance and third-party code execution.
- Implementation owner: Codex for assessment record; Joshua Myers for accountable source/method approval.
- Starting revision/worktree: `02cba004b3ba5fcfa2bd5c4ae707a6a360bc0458`, clean.
- Selected guidance: [verification guide](AGENTIC_VERIFICATION_GUIDE.md), [work-note](../templates/WORK_NOTE.md), [verification](../templates/AGENTIC_VERIFICATION_LOOP.md), and [threat-model](../templates/THREAT_MODEL.md) templates. Threat boundaries are recorded in the [source assessment](G3_ORACLE_CASE_SOURCE_QUALIFICATION.md#trust-boundary-and-controls).

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| G3 source admission | Blocking | Full source inventory, controls, task projection and dependence audit | No unqualified source presented as enrolled |
| Oracle behavior | Blocking | Pinned image base/gold test runs and exact expected IDs | One-case result described accurately; no extrapolation |
| Rights and leakage | Blocking | Dataset card, base-commit license, row fields and image Git inspection | Known leakage and rights limits explicit |
| Data and execution boundary | Blocking | Changed files and network-disabled bounded container commands | No project store access, signatures or arm execution |
| Documentation consistency | Material | ADR, plan, G3 guide, memory and local links | All current-status statements agree |

## Budget and stopping rules

- Two evidence-changing passes: Juliet executable feasibility, then SWE-rebench V2 source screening and one-case base/gold controls.
- Zero provider/study spend; one public image; at most two 360-second, 2-CPU, 2-GiB replay controls.
- Stop with a conditional or negative source verdict when full eligible inventory, leakage-safe projection, grouping or accountable review is absent. Do not create labels to fill those gaps.
- Run the repository quality gate once before publication.

## Iterations

| # | Evidence added | Findings | Decision | Gate |
|---:|---|---|---|---|
| 1 | Juliet v1.3 checksum and one Clang UBSan overflow exemplar; restricted CWE190/191 `_01` stem count | One runtime example works, but answer cues and no uniform oracle; 159 baseline stems are not groups and cannot support the older proposed 400-per-class design | Keep Juliet conditional for a narrow separate benchmark | Archive/probe checks passed |
| 2 | Pinned SWE-rebench builder/sample/image, paper/card, base/gold runs, Git/license read-only checks | One Go task changes from two fail-to-pass failures to passes while all 492 pass-to-pass IDs stay green. Full source inventory, task projection, grouping and governance absent | Record one-case pilot evidence; do not admit G3 source | Controlled replay passed; documentation checks below |

## Finding disposition

| ID | Finding | Severity | Disposition and acceptance check | Owner |
|---|---|---|---|---|
| Q-001 | Public rows contain gold patch, test patch and patch-derived interface; source built for training | Blocking | Freeze and audit a leakage-safe model-visible projection before G3 admission | Joshua Myers |
| Q-002 | Full release not enumerated; repo/task counts do not establish independent groups or sampling probabilities | Blocking | Review complete eligible inventory and prospective selection/observation design | Joshua Myers |
| Q-003 | One base/gold control does not prove casewise oracle stability or all task requirements | Blocking | Predeclare and execute repeated positive, wrong and ambiguous controls on eligible audit set | Joshua Myers |
| Q-004 | Existing two-human/ordinary-audit seal conflicts with proposed one-human oracle variance | Blocking | Amend schema/verifier with negative tests and owner review under ADR-0010 | Joshua Myers |

## Exit

- Stop reason: source screening complete at the declared bound; full source admission lacks required external evidence and owner review.
- Rubric result: one-case oracle claim passes; G3 source-admission gate remains blocked. No project data store or sampling artifact was touched.
- Focused evidence: pinned source and image identities, exact base-commit MIT license, 494 parsed test IDs in both controls, no branch/reflog/unreachable commits in this one image, local Markdown-link and diff checks.
- Full quality gate: `make check` exited 0 outside the sandbox on 2026-09-27. Ruff, Pyright, 2,540 source-tree tests (4 skipped), coverage, export verification, package build, and 1,894 installed-wheel smoke tests passed. The host-permitted run was required because these fixtures bind localhost sockets under the managed sandbox.
- Remaining uncertainty: full-source rights/eligibility, leakage and contamination, independence, feasibility/cost, statistical margins, and amended verifier/owner disposition.
- Human/domain approval: Joshua authorized the single-human direction and requested source qualification; no signed source or cohort approval was provided.
- Durable facts: [source assessment](G3_ORACLE_CASE_SOURCE_QUALIFICATION.md), [ADR-0010](adr/0010-g3-single-human-oracle-study.md), plan, G3 guide and project memory.
