# Work note: WSL2 qualification preparation

- Owner: Josh Myers
- Status: closed — preparation delivered; actual WSL2 qualification pending
- Started: 2026-10-03; review by: 2026-10-17
- Base: `a1cb38bcfcbe332a7db2c22322fa72fb560db672`
- Objective: prepare plan §27.1 setup, read-only preflight and installed-wheel
  qualification procedure while the independent tmux PR runs.
- Scope: preparation only; actual Windows-hosted WSL2, native Windows, release,
  live providers and new execution authority remain outside this batch.
- Risk: material diagnostic/platform work; no runtime admission change.
- Guidance: `PYTHON_ENGINEERING_GUIDE.md`, `AGENTIC_VERIFICATION_GUIDE.md`,
  `../templates/WORK_NOTE.md`, `../templates/AGENTIC_VERIFICATION_LOOP.md` and
  `../templates/THREAT_MODEL.md`; see `WSL2_PREFLIGHT_THREAT_MODEL.md`.

## Blocking rubric and bounds

Recognized WSL2 kernel metadata is required; WSL1, ordinary Linux/macOS, unknown
kernels and unavailable mount metadata reject. Longest covering mounts determine
the resolved selected directories; DrvFS/9p/network/overlay/unknown or read-only
mounts reject, including nested and alias paths. Private selected directories
require current ownership and no group/other permissions. Diagnostics read only
bounded OS metadata and directory metadata, never directory contents, credentials
or environment dumps. A successful report cannot grant execution or support.

Verification: pure negative/positive fixtures, actual read-only local rejection,
lint/typing, source tests and installed-wheel tests. Four correction passes and a
two-hour initial window; no paid calls. Stop after passing checks; report real WSL2
and containment evidence as pending rather than replacing it with fixtures.

## Handoff

Implementation and preparation verification are complete. Ten focused
source tests and ten clean installed-wheel tests passed. Strict typing/lint,
wheel/sdist builds and 491 local documentation targets passed. The installed
diagnostic rejected the real macOS host with exit 2, as required.

The first full source run completed 2,652 tests in 2,195.878 seconds with one error
and four existing optional skips. The error was in the existing
`LaunchAdmissionTests.test_incomplete_campaign_cannot_prepare_launch` setup:
missing `envelope/judge/runtime-generation-start.json`. It did not reproduce in
isolated runs, either normally (4.282 seconds) or with coverage instrumentation
(6.839 seconds). No runtime/test fixture change or gate weakening was made.
The unchanged-code combined retry passed all 2,652 source tests with four existing
optional skips in 2,190.553 seconds, 86% branch-inclusive coverage, static checks,
runtime export verification and wheel/sdist builds. Its installed-wheel run
completed 1,928 tests in 1,476.037 seconds with one existing fixture setup error:
`CampaignSubmissionTests.test_replacement_of_an_existing_slot_is_rejected` failed
with `verified critic quorum was not met`. This case passed in isolation in
1.963 seconds. Neither setup failure has a demonstrated root cause; no shared
fixture or runtime check was changed. The first failures remain recorded rather
than being treated as passing runs.

The failed installed-wheel gate was retried alone against the same frozen
code/artifact: `make smoke` exited 0; all 1,928 tests passed with no skips in
1,411.269 seconds. Every constituent quality-gate check passed on the unchanged
code, but neither original `make check` invocation exited successfully. No source
gate was unnecessarily repeated after its passing run. The initial two-hour
window was exceeded during verification; completion was limited to the existing
gate, with no additional implementation iterations or paid calls.

No Windows-hosted WSL2 runner is available in this macOS workspace. The tmux PR is
independent and is not merged or copied into this branch.

## Close and promote

The runbook, diagnostic, ten source/installed-wheel tests, and package-smoke wiring
complete the preparation slice. Documentation links and diff checks cover the
final prose-only closeout. Durable retrieval was added to `PROJECT_MEMORY.md`
under `platform.wsl2-preparation`; the plan and roadmap retain the actual §27.1
platform gates. Temporary focused-test environments were cleaned up; disposable
quality-gate logs remain outside Git. Prepared on
`feat/wsl2-qualification-preparation`; remote publication is a separate step. No
provider calls, study, merge, release or publication occurred. The original
checkout's separate plan amendment remains untouched.
