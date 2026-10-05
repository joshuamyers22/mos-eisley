# Open PR integration, 2026-10-05

- Status: active
- Owner: Josh Myers; integration by Codex under the explicit request to merge all
  open PRs and correct errors.
- Starting main: `5a6be4e`; work is isolated from existing modified checkouts.
- Scope: PRs #266, #268, #270, #272, #273, #275, #276, #277, #278, #279,
  #280, #281, #282, #283, #284 and newly opened #285.

## Objective and invariants

Merge all requested histories while preserving current provider fixes, signed
qualification scope, deferred-study decisions, frozen dependencies and existing
conversation evidence. Candidate platform APIs remain inert at their public
admission boundaries. No live provider, study, credential, deployment or application
activation is part of this integration. Existing uncommitted edits are preserved.

## Guidance and acceptance

Selected [agentic verification guide](AGENTIC_VERIFICATION_GUIDE.md),
[verification loop template](../templates/AGENTIC_VERIFICATION_LOOP.md),
[Python guide](PYTHON_ENGINEERING_GUIDE.md),
[work note template](../templates/WORK_NOTE.md), and existing feature contracts.
Blocking criteria: lost current behavior or evidence, broadened authority, broken
source/wheel tests, static checks, dependency export, build or required CI.
Use focused boundary tests before one combined `make check`; fix failures and
repeat affected checks. Native Windows/Linux checks remain CI evidence rather than
local macOS claims. No paid compute or model review is authorized. Stop on green
local and required remote gates; external domain decisions remain separate from
this user-authorized merge.

## Integration decisions

- Retain all package smoke selections from the stacked platform and Git PRs.
- Reconcile historical model-role and GHP proposals against current milestone,
  provider and deferred-study decisions; retain the exact secret-scan exceptions.
- Keep current Anthropic 1.x compatibility, citation contracts and sealed campaign
  settlement behavior when the conversation draft contains older alternatives.
- Preserve the qualified workspace diff panel as the default. The draft's distinct
  Git-review/findings panel is selected explicitly with `--git-review-panel`.
  Their snapshot and attachment formats remain distinct; saved records retain the
  original format, bounded envelope and content-bound request admission. Mixed
  formats in one message refuse. Both panels use the shared terminal/controller.
- Port goal, branch, loop, agent and review-scope reports into the default panel.
  New feature histories remain included; no existing test is removed. The draft's
  panel tests target its explicitly named panel class.

## Verification

Focused workspace-panel, Git-review-panel, timer-driver and attachment persistence
checks passed. The scheduled-event branch appeared during integration and adds
its bounded source/ingress transports. Recorded scheduling and branching now
explicitly refuse a live-chat controller, preserving the draft qualification scope.
Pending combined source/wheel gate and required CI. Disposable logs live outside
Git. The final closeout will record actual counts, failures and platform skips.
