# Work Note: G3 full oracle source qualification

- Status: closed for audit; G3 source enrollment remains open
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Last updated (UTC): 2026-09-28
- Review or delete by: G3 source and method disposition
- Related decision: [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md)

## Objective and completion evidence

- Intended outcome: determine whether a pinned SWE-rebench V2 source can support the prospective, narrow, single-human objective-oracle G3 claim, and close every source-level gate that the available evidence permits.
- Invariants: never access project sampling registry, custodian mapping, label store or outcome store; never infer unknown probabilities, groups, labels or splits; never turn public benchmarks into real production outcomes; no provider/study-arm dispatch or signed study label from this audit.
- Evidence for qualification: complete source inventory and rights screen; frozen leakage-safe task projection; independently tested oracle controls on a declared audit frame; reviewed assignment-unit grouping and feasibility; exact arm and cost review; prospective single-human verifier amendment and Joshua's signed outcome-blind source/method disposition.
- Risk class: high-risk statistical governance, third-party code execution and source rights.
- Resource ceiling: one 429 MB pinned public release; at most 2 GB of temporary source/audit files beyond the existing Docker image; zero provider spend; no new image pull without checking remaining disk. Public-source inspection and bounded offline controls only. Stop if disk falls below 3 GB, a blocking source defect is established, or accountable owner review is the remaining gate.
- Selected guidance: [bounded verification guide](../docs/AGENTIC_VERIFICATION_GUIDE.md), [verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), [work-note template](../templates/WORK_NOTE.md), and [threat-model template](../templates/THREAT_MODEL.md). The source trust boundary is in the [qualification record](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION.md#trust-boundary-and-controls).

## Context retrieved

[Project brief](../PROJECT_BRIEF.md), [project memory](../PROJECT_MEMORY.md), [G3 guide](../docs/G3_CONTEXT_STUDY.md), [source assessment](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION.md), [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md), and [production outcome contract](../docs/PRODUCTION_OUTCOME_ACCEPTANCE.md).

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-27 | observation | Prior assessment validated one public base/gold replay but did not enumerate the full eligible frame or test leakage-safe projection, repeated oracle controls, grouping or feasibility. | [Assessment](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION.md) | Inspect pinned full release. |
| 2026-09-27 | observation | Pinned Parquet is 428,839,266 bytes according to the source host. Local disk had 8.1 GiB free before download. | [Source file](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/475dd5e8703bb5fb22dd3c60b5d038b019eba1e0/data/train-00000-of-00001.parquet) | Verify SHA-256 and enumerate safe metadata. |
| 2026-09-27 | observation | Full Parquet SHA-256 matched the source's `0e0bf9355f892ad74ae98d4e1c404f39fd6654a8e351ee3e6ab162e4a64cd3ad`; 32,079 unique IDs, 3,617 repository names, 20 languages, 16 non-null license strings. License is absent for 348 rows and is `custom-check-github` for 5,038. Forty-six rows have no problem statement. | Pinned temporary Parquet; DuckDB 1.5.5 read-only aggregate | Screen dependence and issue-text overlap. |
| 2026-09-27 | artifact | Deterministic, ID-sorted source-identifier JSONL lists only public instance ID, repository, base commit, language, license metadata and image name for all 32,079 rows. It has no issue text, patch, oracle outcome, label, group, probability or split, and grants no sampling authority. SHA-256 `82a6ab72ef33b26a1e49b5f8f3d1c9a4e7076ad4cb4db2dc4f041b4725460616`; 8,009,942 bytes; stored outside Git in `/private/tmp`. | Pinned temporary Parquet; deterministic ordered projection | Keep separate from project evaluation stores. |
| 2026-09-27 | observation | The public rows contain 30,836 distinct repository/base-commit pairs; 2,319 rows lie in 1,076 repeated pairs. Code-patch hashes are unique for 31,901 rows and test-patch hashes for 31,580. These are source overlaps, not inferred study independence groups. | Full-release structural aggregate | Keep assignment-unit grouping open. |
| 2026-09-27 | observation | An exact-string screen found a 40–300-character added code-patch line inside the problem statement for 681 rows, a test-patch line for 1,466, and either for 2,065. Overlap is a review flag rather than a ground-truth leakage label; the screen cannot detect semantic disclosure or model pretraining exposure. | Full-release bounded line-overlap scan | Require audited projection and case review. |
| 2026-09-27 | observation | A provisional Go feasibility filter (named MIT/Apache/BSD/ISC license metadata, nonempty statement, exact `go test -v ./...`, 1–10 fail-to-pass IDs, at most 500 pass-to-pass IDs and 100,000 characters each for code/test patches) retains 975 rows across 163 repository names. Thirty-five of those rows trigger the exact-line overlap screen. This filter is a capacity diagnostic, not an eligible-source inventory or a probability/group/label assignment. | Full-release aggregate and overlap screen | Test bounded oracle controls. |
| 2026-09-27 | observation | In the one previously selected Go case, repeated base/test, gold/test and no-op-wrong/test runs each produced 494 unambiguous JSON test names. The two target IDs failed/passed/failed as expected while all 492 other IDs passed in each run. Removing a required gold event made the independent parser reject the log. | [Full audit](../docs/G3_SWE_REBENCH_FULL_SOURCE_AUDIT.md), temporary control script SHA-256 `134bfa547ca3687482be0664c1f18e739665a6eee627cd8de32c6798c14375bb` | Keep the claim confined to one convenience case. |
| 2026-09-27 | decision | A full identifier inventory and one-case oracle do not close per-case rights, task leakage, broad oracle, dependence, six-arm feasibility or single-human governance. Recommend no G3 enrollment from this release now. | [Full audit](../docs/G3_SWE_REBENCH_FULL_SOURCE_AUDIT.md) | Record owner-review gates. |
| 2026-09-28 | verification | Local links and staged whitespace check passed. `make check` exited 0: Ruff, Pyright, 2,540 source-tree tests (4 skipped), 88% coverage, export verification, wheel build and 1,894 installed-wheel smoke tests. | [Verification record](../docs/G3_SWE_REBENCH_FULL_SOURCE_AUDIT_VERIFICATION.md) | Publish the reviewable negative admission recommendation. |

## Handoff

- Current state: full-release source audit and verification complete; no study source admitted. Publication on PR #241 follows this note.
- Next smallest safe action: Joshua reviews the negative admission recommendation and, for a future positive decision, defines a bounded source subset and funds per-case rights, task-view and oracle validation before the statistical-method disposition.
- Blocker and required authority/input: Joshua's accountable source/method disposition cannot be issued by the agent.
- Checks already run: source-plan and tool inspection, file and identifier digests, full structural and overlap screens, bounded Docker controls, local links and staged diff, full `make check`; no project evaluation stores accessed.

## Close and promote

- Outcome and verification: full structural audit and one-case independent oracle control pass; release-wide G3 source admission fails on unresolved rights, leakage, broad oracle, dependence, feasibility and governance. Full repository gate passed.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.g3.feasibility`.
- Decision promoted to ADR/documentation: [full audit](../docs/G3_SWE_REBENCH_FULL_SOURCE_AUDIT.md), [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md), [plan](../docs/mos-eisley-plan.md), and [G3 guide](../docs/G3_CONTEXT_STUDY.md).
- Regression test, issue, or improvement-plan link: no product code changed; prospective source and verifier work remains under ADR-0010.
- Temporary artifacts removed: none; public source and control logs remain outside Git in `/private/tmp` for owner review.
