# Work Note: defer G3 studies until production

- Status: active
- Owner: Joshua Myers
- Started (UTC): 2026-09-28
- Last updated (UTC): 2026-09-28
- Review or delete by: first production study admission
- Related decision: [ADR-0011](../docs/adr/0011-defer-studies-until-production.md)

## Objective and completion evidence

- Intended outcome: record Joshua's direction that Mos Eisley runs no study
  before it is in production.
- Required invariants: prelaunch source audits and product tests grant no study
  authority; real owner-task outcomes remain necessary for production claims;
  G3/G5 dependent capabilities stay gated; launch alone grants no study authority.
- Evidence that will show completion: plan, roadmap, G3 guide, linked ADRs and
  outcome contract agree; links and repository checks pass; no protocol or
  sampling artifact is changed.

## Context retrieved

Selected `templates/ADR.md`, `templates/WORK_NOTE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md` and
`templates/AGENTIC_VERIFICATION_LOOP.md` under `AGENTS.md`.
Read `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, plan §26.4/§26.6,
the roadmap, ADR-0008/0009/0010, the G3 guide, execution-view audit and
production-outcome contract. The earlier source audits are engineering
diagnostics, not executed studies.

## Verification rubric and budget

| Dimension | Blocking condition | Decision evidence |
|---|---|---|
| Start gate | Any study can enroll or run before actual production operation | Plan, roadmap and ADR-0011 agree |
| Outcome boundary | Public or fixture result becomes production efficacy evidence | Outcome contract and G3/G5 guides preserve real-task requirement |
| Release authority | Deferral silently waives a product or G3/G5 capability gate | Plan and ADR retain the separate gates |
| Documentation | Broken links or contradictory current guidance | Relative-link check, `git diff --check`, repository gate |

One documentation batch, no provider or study spend, one `make check` run.
Stop when the corrected plan is internally consistent and the quality gate is
reported; any future study still needs Joshua's separate prospective approval.

## Observations and attempts

| Type | Observation, action, or concise result | Evidence |
|---|---|---|
| observation | The old G3 delivery row still allowed a preproduction utility study; ADR-0010 described a possible preproduction oracle claim. | [plan §26.4](../docs/mos-eisley-plan.md#264-delivery-order-and-accountable-gates); [ADR-0010](../docs/adr/0010-g3-single-human-oracle-study.md) |
| decision | Defer all G3, G5, oracle and continuous-evaluation study execution until a documented production launch; keep study admission separate. | [ADR-0011](../docs/adr/0011-defer-studies-until-production.md) |
| verification | All 14 edited Markdown files have resolving relative links and `git diff --check` passes. Local `make check` stopped after 2,540 tests with six CLI subprocess timeouts and one memory-refresh error; build/smoke were not reached. All seven named tests passed when rerun alone in 46.7 seconds. | Local checks; full log retained outside Git |

## Handoff

- Current state: plan correction verified locally except for a full-suite local
  resource-sensitive test failure; new-head PR CI remains to be checked.
- Next smallest safe action: push the documentation batch and inspect PR CI.
- Blocker and required authority/input: actual production launch and separately
  approved study inputs before any cohort.
- Checks already run: document search, source review, relative-link check,
  `git diff --check`, full local `make check` (failed as described), and seven
  focused tests (passed). No full local pass is claimed.
