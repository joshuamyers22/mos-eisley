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
review and publication. Four hours active implementation, four hours per native
combined quality gate (five-hour job ceiling), and three bounded bootstrap repairs, followed by one evidence-driven fixture-portability repair. No paid providers or
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

- Attempt 2: [run 39866622928](https://github.com/joshuamyers22/mos-eisley/actions/runs/39866622928)
  completed WSL2 boot, package installation and pinned uv checksum verification.
  Windows path backslashes were consumed by WSL's default shell transport before
  `wslpath`; no tests ran on that target. Use explicit `--exec` argv transport for
  every Linux command and require a literal backslash/space/quote round trip before
  cloning or testing. Cancel the superseded Linux candidate and retain both setup
  attempts; neither is qualification success.

- Attempt 3: [run 39867759899](https://github.com/joshuamyers22/mos-eisley/actions/runs/39867759899)
  passed the literal argv round trip and reached cloning. Git correctly rejected
  Linux access to Windows-owned checkout metadata. Transfer a Windows-created,
  hash-checked Git bundle into ext4 and clone from the Linux-owned bundle. Preserve
  the ownership guard; do not set `safe.directory=*` or exempt the Windows source.
  A portable regression deletes the source repository before cloning its copied
  bundle and verifies exact commit, clean checkout and no object alternates.

- Active attempt 4: [run 39869875447](https://github.com/joshuamyers22/mos-eisley/actions/runs/39869875447),
  exact candidate `93f264d25b9680f31d9c5a52756428dd9578f9ed`.
  Native Linux job `120141331874` and actual Windows/WSL2 job `120141332305`
  were in progress when first recorded. The portable tool suite has five passing cases; no
  runtime/source code changed during the setup repairs. Native completion and
  artifact validation are still required.

- The isolated-wheel evidence runner also passed all 116 focused cases locally,
  with zero skips in 122.700 seconds, from a separate virtual environment and
  copied fixtures outside the checkout. This verifies the runner/fixture layout;
  native qualification still depends on the two active target jobs.

- Attempt 4 WSL2 completed 3,853 source tests in 5,862.883 seconds and failed
  five private-directory negative fixtures (six reported failures/errors because
  one test runs through two classes). The bootstrap's umask 077 masked their
  `mkdir(mode=0755)` to 0700. The application correctly admitted private directories;
  fixtures must explicitly chmod their deliberately unsafe directory. No privacy
  check or application authority is relaxed.
- Observed source duration is about 98 minutes on this runner. Revise the combined
  source/wheel gate ceiling from two to four hours, with a five-hour job ceiling
  and 15-minute focused-case commands. This is a CI runtime allowance, not a change
  to product acquisition, cancellation, spend or authorization limits. Retain the
  failed native attempt; rerun focused permission cases under umask 077, then the
  complete exact-candidate native gates.

- All five repaired negative permission tests pass under umask 077 locally in
  2.815 seconds, including the native loopback OAuth fixture. The first local
  OAuth run was blocked by the sandbox's socket policy; its permitted native
  rerun passed. Ruff/format and strict tool typing pass. Application code is
  unchanged; the deliberately unsafe fixture modes are now explicit on every OS.
- Attempt 4 is superseded by the corrected fixture/budget candidate. Run both
  full native gates again; do not treat the failed WSL source run as acceptance.

## Completion evidence

Pending native runs and evidence review.
