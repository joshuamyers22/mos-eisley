# Work Note: G3 oracle case-source qualification

- Status: closed for source screening; G3 qualification remains open
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Last updated (UTC): 2026-09-27
- Review or delete by: next G3 source and method review
- Related decision: [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md)

## Objective and completion evidence

- Intended outcome: decide whether an identified, pinned public case source has enough independently checkable oracle evidence and task fit to enter the proposed narrow G3 study.
- Required invariants: no project sampling, custodian, label, or outcome-store access; no inferred groups, probabilities, labels, or splits; no fabricated signatures or empirical seal; source outputs never copied into a sampling artifact.
- Evidence of completion: source identity and rights, controlled oracle controls, task-view leakage, frame and grouping limits, a clear admission verdict, and a documented owner-review gate.
- Risk class: high-risk statistical governance and untrusted public-code execution.
- Resource ceiling: zero provider or study spend; one public task image, two network-disabled container runs at most 360 seconds each, 2 CPUs and 2 GiB per run; stop on a nondecisive replay or source mismatch.

## Context retrieved

[Project brief](../PROJECT_BRIEF.md), [project plan](../docs/mos-eisley-plan.md),
[G3 guide](../docs/G3_CONTEXT_STUDY.md), [Juliet audit](../docs/G3_JULIET_SOURCE_AUDIT.md),
[ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md),
[verification guide](../docs/AGENTIC_VERIFICATION_GUIDE.md),
[work-note template](../templates/WORK_NOTE.md),
[verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), and
[threat-model template](../templates/THREAT_MODEL.md).

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-27 | observation | NIST Juliet's inspected CWE190 overflow case gives a controlled sanitizer signal, but the CWE190/191 baseline functional stems number at most 159 and do not establish independent groups. | [Juliet audit](../docs/G3_JULIET_SOURCE_AUDIT.md), temporary probe outside Git | Assess a repository task source with executable tests. |
| 2026-09-27 | observation | SWE-rebench V2 publishes 32,079 issue-linked tasks from 3,617 repositories with base commits, code/test patches, fail-to-pass IDs and images; its paper states three-run stable test outcomes. These are source claims, not G3 inventory or grouping evidence. | [Paper](https://arxiv.org/html/2602.23866v2), [dataset card](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/main/README.md) | Replay one task under controls. |
| 2026-09-27 | attempt | Pinned builder commit `c71902a8cf8d2b725f63d51f199f4d3e56f68d2d` and 20-task sample commit `9a7cd16b2431fc9f0abaf4c359e21fd3fae12ae3`; selected the public Go task `mgechev__revive-1408` for a bounded probe. Public source and replay files live only in `/private/tmp`, not a project sampling artifact. | [Builder](https://github.com/SWE-rebench/SWE-rebench-V2), [sample](https://huggingface.co/datasets/ibragim-bad/SWE-rebench-V2-sample) | Record replay result and source verdict. |
| 2026-09-27 | observation | Pinned Go image: base plus test patch failed both published fail-to-pass IDs while 492 pass-to-pass IDs passed; gold plus test patch passed all 494 parsed IDs. Read-only Git inspection found no branch/reflog or unreachable commits in this one image. The exact base-commit license is MIT. | [Qualification record](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION.md) | Keep this result scoped to one case. |
| 2026-09-27 | decision | SWE-rebench V2 remains a candidate; one case supports only a controlled pilot design. Full G3 source admission is denied pending eligible frame, task-view, oracle-control, grouping, feasibility and accountable review evidence. | [Qualification record](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION.md) | Owner reviews source and method before any empirical seal. |

## Handoff

- Current state: source screening complete; no G3 source, cohort, label, split or arm admitted.
- Next smallest safe action: audit a complete pinned candidate inventory and model-visible projection, then validate predeclared positive, negative and ambiguous oracle controls on an auditable source subset.
- Blocker and required authority/input: accountable owner statistical/source review and a complete prospective eligible frame before G3 enrollment.
- Checks already run: source snapshot identity, sample schema, builder evaluation path, controlled base/gold replay, read-only image Git/license inspection, local-link and diff checks, and a passing `make check` (2,540 source tests plus 1,894 installed-wheel smoke tests); no project sampling workflow invoked. See [verification](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION_VERIFICATION.md).

## Close and promote

- Outcome and verification: one oracle case validated for screening; full source not qualified; see [verification](../docs/G3_ORACLE_CASE_SOURCE_QUALIFICATION_VERIFICATION.md).
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.g3.feasibility`.
- Decision promoted to ADR/documentation: [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md), [plan](../docs/mos-eisley-plan.md), and [G3 guide](../docs/G3_CONTEXT_STUDY.md).
- Regression test, issue, or improvement-plan link: this is a source assessment, not a code change; the verifier amendment remains open under ADR-0010.
- Temporary artifacts removed: replay materials are retained temporarily in `/private/tmp` for local review; they are outside Git and contain no project sampling data.
