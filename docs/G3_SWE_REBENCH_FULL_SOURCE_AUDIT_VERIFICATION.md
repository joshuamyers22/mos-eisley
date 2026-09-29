# Agentic Verification Loop: SWE-rebench full-source admission

## Objective and authority

- Requirement: finish the G3 oracle-backed case-source qualification requested by Joshua.
- Outcome: give an accountable reviewer an exact source inventory and an honest G3 admission decision.
- Invariants: no project sampling registry, custodian mapping, label store or outcome store access; no invented probability, group, label or split; no public benchmark relabeled as production evidence; no study-arm or provider dispatch.
- Risk class: high-risk statistical governance, third-party code and rights.
- Owner: Codex for source audit; Joshua Myers for source and statistical-method disposition.
- Starting revision/worktree: `98dcb0c0e32fc7f3ce1aec1ce4cff466c963560c`, clean.
- Selected guidance: [bounded verification guide](AGENTIC_VERIFICATION_GUIDE.md), [work note](../notes/G3_FULL_ORACLE_SOURCE_QUALIFICATION.md), [verification](../templates/AGENTIC_VERIFICATION_LOOP.md) and [threat model](../templates/THREAT_MODEL.md) templates.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Exact source frame | Blocking | Pinned full Parquet SHA-256 and 32,079-row structural/rights screen | No sample or paper count passed off as eligible cases |
| Oracle truth | Blocking | Base/gold/wrong controls, independent JSON parser and truncated-log fault | One-case claim exact; no release-wide extrapolation |
| Leakage and dependence | Blocking | Patch-line overlap, model-visible field review, duplicate base/patch counts | Unknown task-view or groups remain open |
| Rights and governance | Blocking | Dataset/repository licensing and ADR-0010 verifier status | No G3 enrollment without audited rights and owner review |
| Data and execution safety | Blocking | Temporary public manifest, bounded Docker settings, staged files | No private project store, study arm or provider use |
| Documentation integrity | Material | Local links, diff, repository gate | Current status agrees across plan, ADR, G3 guide and memory |

## Budget and stopping rules

- Two evidence-changing passes: full pinned release structure and exposure screen; then independent one-case oracle controls.
- One 429 MB public source file, no new image pull, at most three additional 360-second offline container runs, 2 CPUs and 2 GiB each, zero provider/study spend.
- Stop on a blocking admission gap or when accountable owner review is required; record the negative decision and exact remaining gates.

## Iterations

| # | New evidence | Finding | Disposition | Gates |
|---:|---|---|---|---|
| 1 | Full pinned file, source identifier manifest and structural/rights/overlap aggregates | Unique IDs, but 5,386 unknown/custom license rows, repeated base/patch structure and 2,065 exact added-line flags | Structural source inventory only; no eligible case frame | SHA-256 matched via shell and Python; independent JSONL shape/order/unique-ID and 32,079-row/3,617-repository check passed |
| 2 | Network-disabled repeat base/gold and no-op wrong-repair controls with a separate Go JSON parser | Expected fail/pass/fail on two related target IDs; 492 other IDs pass; no ambiguity; truncated gold log rejected | Qualify one behavior for bounded calibration, not source admission | Focused controls and `make check` pass |

## Findings and trust boundary

| ID | Asset and failure mode | Severity | Control and residual status | Owner |
|---|---|---|---|---|
| S-001 | Public row can disclose solution/test patches or inject instructions through issue text or repository files | Blocking | Raw fields excluded from any future task projection; full projection and case review absent | Joshua Myers |
| S-002 | Third-party license string may differ from base-commit rights | Blocking | 5,386 unknown/custom rows counted; no row accepted from metadata alone | Joshua Myers |
| S-003 | Generated test parser, flaky test or missing event could report false success | Blocking | One case cross-checked with JSON parser, wrong repair and truncated log; broad audit absent | Joshua Myers |
| S-004 | Repeated repository/base/patch structures could make nominal cases dependent | Blocking | Counts disclosed; no independence grouping inferred | Joshua Myers |
| S-005 | One-human oracle variance could be mistaken for two independent human graders | Blocking | Existing verifier left unchanged and no signed labels issued | Joshua Myers |

Public file and container inputs cross an untrusted-source boundary. The image ran without network, host credentials or project-store mounts, with CPU/memory/process limits, dropped capabilities and `no-new-privileges`. Local public logs and source identifier metadata remain outside Git. The manifest contains no issue text, model response, outcome, label, group, probability or split, and is not a sampling receipt. Remaining risks include model pretraining exposure, Docker/image supply-chain flaws, source rights and casewise oracle defects.

## Exit

- Stop reason: source-level blocking findings and accountable review remain.
- Rubric result: integrity and one-case oracle checks pass; G3 source admission fails.
- Focused checks: full file digest by shell and Python, row/schema and aggregate scans, standard-library manifest shape/order/count/digest check, independent JSON controls, and local relative-link/diff checks passed.
- Full quality gate: `make check` exited 0 on 2026-09-28 UTC for the combined documentation batch: Ruff, Pyright, 2,540 source-tree tests (4 skipped), 88% coverage, export verification, wheel build and 1,894 installed-wheel smoke tests (OK). The host-permitted run was needed because repository fixtures bind localhost sockets.
- Human/domain approval: Joshua authorized the audit direction; no signed source/method disposition, cohort approval, study spend or production use is inferred.
- Durable facts: [full audit](G3_SWE_REBENCH_FULL_SOURCE_AUDIT.md), [ADR-0010](adr/0010-g3-single-human-oracle-study.md), [G3 guide](G3_CONTEXT_STUDY.md), plan and project memory.
