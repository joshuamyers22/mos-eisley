# Work note: native review platform qualification

- Status: active
- Owner: repository maintainer, assisted by Codex
- Started: 2026-10-22
- Review by: next release qualification
- Related: project plan §31.7; production template 8879be48f3b760e65f6bed32f8740314fe92910d

## Objective and invariants

Run the exact managed-worktree review candidate on native Linux and actual
Windows-hosted WSL2, from source and an independently installed wheel. Retain
candidate and artifact identity, actual platform observations, commands, test
counts/skips and outcomes. Never infer WSL2 from Ubuntu or a mocked kernel.
Preserve scoped read authority, source freshness, ownership, disabled helpers,
unchanged checkout, frozen-brief parity, quorum, budgets and cancellation.

Risk class: security-sensitive qualification tooling. Host observations are
runtime evidence, not new execution, provider, release or production approval.
Use synthetic fixtures only. No credentials, sampling stores or live providers.
No native-Windows support, arbitrary filesystem, containment or release claim.

## Guidance and context

Selected AGENTS.md, Python engineering and agentic verification guides, threat
model, verification-loop and work-note templates. Read the project brief/memory,
README, §31.7, WSL2 runbook/preflight, existing CI and source/wheel scope tests.
The previous macOS candidate passed 3,853 source and 2,831 wheel tests; that evidence
does not establish either requested native target.

## Budget and stopping rules

Three passes: platform/runner admission; exact source/wheel qualification; evidence
review and publication. Four hours active implementation, two hours per native
quality job, and at most three bounded setup/failure repairs. No paid providers or
premium runner labels. Fail closed on missing host provenance, WSL1, root user,
non-Linux storage or skipped required review cases. If actual WSL2 cannot start,
retain the failed attempt and request a reachable Windows host instead of claiming
completion. Keep broader platform and exact live-target release gates separate.

## Observations and attempts

- Current host is Darwin. GitHub runner inventory contains zero self-hosted runners.
- Existing CI covers Ubuntu source/wheel but does not run on feature-branch pushes
  and contains no actual WSL2 job. GitHub's Windows Server 2025 image advertises
  WSL2; actual startup and host/distro version evidence are still required.

- Qualification tooling now requires real non-root Linux/ext4 observations,
  matching Windows host-side WSL2/distro/candidate evidence, a clean exact commit,
  passing source/wheel quality summaries and exact source/wheel module bytes.
- Four evidence-validation fault tests pass; Ruff/format and strict tool Pyright
  pass. The eight focused review modules passed 116 cases with no skips locally
  in 117.021 seconds. These local checks do not qualify either native target.
- A candidate branch push is needed to execute the new target workflow; the
  candidate is not a release or completion claim. Each target runs `make check -j1`
  plus the same skip-free source/isolated-wheel review cases.

- Attempt 1: [run 39865165385](https://github.com/joshuamyers22/mos-eisley/actions/runs/39865165385)
  installed and booted actual Windows-hosted WSL2 and retained host observations,
  but rejected the CRLF Bash bootstrap from the Windows checkout before tests.
  Normalize embedded Bash text to LF; cancel the obsolete Linux run and rerun both
  targets on the corrected exact candidate. No runtime gate was weakened.

## Completion evidence

Pending native runs and evidence review.
